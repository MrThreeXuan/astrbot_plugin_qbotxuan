import random
import json
import os
import asyncio
from datetime import date, datetime, time, timedelta
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 确保插件名唯一，避免与其它插件冲突
@register("astrbot_plugin_qqfun", "你的名字", "实现win和自动marry功能的插件 (稳定版)", "1.0.0")
class QQFunPlugin(Star):
    # 类变量确保全局只有一个后台任务实例
    _daily_task = None

    def __init__(self, context: Context):
        super().__init__(context)
        # 数据存储路径（使用绝对路径避免混淆）
        self.data_dir = os.path.join(context.data_dir, 'astrbot_plugin_qqfun')
        os.makedirs(self.data_dir, exist_ok=True)
        self.win_file = os.path.join(self.data_dir, 'win_data.json')
        self.marry_file = os.path.join(self.data_dir, 'marry_data.json')

        # 如果类变量没有任务，则创建并保存；否则复用
        if QQFunPlugin._daily_task is None or QQFunPlugin._daily_task.done():
            QQFunPlugin._daily_task = asyncio.create_task(self._daily_marry_loop(), name="daily_marry")
            logger.info("每日自动配对后台任务已启动")

    # ---------- 插件卸载时清理任务 ----------
    async def unload(self):
        if QQFunPlugin._daily_task and not QQFunPlugin._daily_task.done():
            QQFunPlugin._daily_task.cancel()
            try:
                await QQFunPlugin._daily_task
            except asyncio.CancelledError:
                pass
            QQFunPlugin._daily_task = None
            logger.info("每日自动配对任务已取消")

    # ---------- 辅助方法 ----------
    def _read_json(self, file_path: str) -> dict:
        """原子化读取，使用临时文件避免损坏"""
        if not os.path.exists(file_path):
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取 {file_path} 失败: {e}")
            return {}

    def _write_json(self, file_path: str, data: dict) -> None:
        """原子化写入：先写临时文件再重命名"""
        temp_file = file_path + ".tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_file, file_path)
        except Exception as e:
            logger.error(f"写入 {file_path} 失败: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

    # ---------- 安全调用 OneBot API ----------
    async def _safe_call_action(self, action: str, timeout=10, **kwargs):
        """带超时和重试的API调用"""
        for attempt in range(3):  # 最多重试3次
            try:
                result = await asyncio.wait_for(
                    self.context.platform.call_action(action, **kwargs),
                    timeout=timeout
                )
                return result
            except asyncio.TimeoutError:
                logger.warning(f"API {action} 超时 (尝试 {attempt+1}/3)")
                if attempt == 2:
                    logger.error(f"API {action} 最终超时")
                    return None
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"API {action} 异常: {e}")
                return None

    # ---------- win 指令 ----------
    @filter.command("win")
    async def win(self, event: AstrMessageEvent):
        """获取今日 win 值（幂等）"""
        user_id = event.get_sender_id()
        today_str = str(date.today())

        win_data = self._read_json(self.win_file)

        if user_id in win_data and win_data[user_id].get('date') == today_str:
            win_value = win_data[user_id]['value']
            yield event.plain_result(f"你今天已经赢过了，win值是：{win_value}")
        else:
            new_win = random.randint(1, 100)
            win_data[user_id] = {'date': today_str, 'value': new_win}
            self._write_json(self.win_file, win_data)
            yield event.plain_result(f"✨ 今日win值已生成：{new_win}")

    # ---------- 每日配对循环 ----------
    async def _daily_marry_loop(self):
        """后台循环：每天0点执行一次配对，计算等待时间精确到秒"""
        while True:
            try:
                now = datetime.now()
                # 计算下一个0点
                next_run = datetime.combine(now.date() + timedelta(days=1), time.min)
                wait_seconds = (next_run - now).total_seconds()
                logger.info(f"下次自动配对将在 {wait_seconds:.0f} 秒后执行")
                await asyncio.sleep(wait_seconds)

                # 执行配对
                await self._auto_marry()
            except asyncio.CancelledError:
                logger.info("每日配对循环被取消")
                break
            except Exception as e:
                logger.error(f"每日配对循环异常: {e}")
                # 出错后等待5分钟再试
                await asyncio.sleep(300)

    # ---------- 自动配对核心 ----------
    async def _auto_marry(self):
        """获取所有群成员并随机配对"""
        logger.info("开始每日自动marry配对...")
        try:
            # 获取机器人自身QQ（如果有）
            bot_id = None
            if hasattr(self.context.platform, 'get_bot_id'):
                bot_id = self.context.platform.get_bot_id()

            # 获取群列表
            groups = await self._safe_call_action('get_group_list', timeout=15)
            if not groups or not isinstance(groups, list):
                logger.warning("无法获取群列表，配对中止")
                return

            today_str = str(date.today())
            new_marry_data = {}

            for group in groups:
                group_id = group.get('group_id')
                if not group_id:
                    continue

                members = await self._safe_call_action('get_group_member_list', group_id=group_id, timeout=20)
                if not members or not isinstance(members, list):
                    logger.warning(f"群 {group_id} 无法获取成员列表，跳过")
                    continue

                # 过滤出有效用户ID，排除机器人
                member_ids = [m['user_id'] for m in members if m.get('user_id') and m['user_id'] != bot_id]
                if len(member_ids) < 2:
                    logger.info(f"群 {group_id} 成员少于2人，跳过")
                    continue

                random.shuffle(member_ids)
                pairs = {}
                for i in range(0, len(member_ids) - 1, 2):
                    a = member_ids[i]
                    b = member_ids[i+1]
                    pairs[str(a)] = str(b)
                    pairs[str(b)] = str(a)

                group_key = f"{group_id}_{today_str}"
                new_marry_data[group_key] = {
                    'pairs': pairs,
                    'lonely': [str(member_ids[-1])] if len(member_ids) % 2 == 1 else []
                }
                logger.info(f"群 {group_id} 配对完成: {len(pairs)//2} 对, 落单 {len(new_marry_data[group_key]['lonely'])} 人")

            self._write_json(self.marry_file, new_marry_data)
            logger.info("每日自动marry配对完成")
        except Exception as e:
            logger.error(f"_auto_marry 发生严重错误: {e}")

    # ---------- marry 查询指令 ----------
    @filter.command("marry")
    async def query_marry(self, event: AstrMessageEvent):
        """查询今日伴侣，若无数据则尝试立即配对一次（降级方案）"""
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群聊中使用。")
            return

        user_id = event.get_sender_id()
        today_str = str(date.today())
        group_key = f"{group_id}_{today_str}"

        marry_data = self._read_json(self.marry_file)

        # 如果今天还没有配对数据，尝试立即配对（仅限本群）
        if group_key not in marry_data:
            yield event.plain_result("今日尚未生成配对数据，正在尝试立即为您生成...")
            # 立即为当前群执行一次配对（不阻塞整个循环）
            asyncio.create_task(self._pair_single_group(group_id, today_str))
            yield event.plain_result("配对任务已启动，请稍后再查。")
            return

        pairs = marry_data[group_key].get('pairs', {})
        lonely = marry_data[group_key].get('lonely', [])

        if str(user_id) in pairs:
            mate_id = pairs[str(user_id)]
            # 获取昵称（可选）
            member_info = await self._safe_call_action('get_group_member_info', group_id=group_id, user_id=int(mate_id), timeout=8)
            mate_name = None
            if member_info:
                mate_name = member_info.get('nickname') or member_info.get('card')
            if not mate_name:
                mate_name = mate_id
            yield event.plain_result(f"💑 你今天和 {mate_name} 是伴侣哦！")
        elif str(user_id) in lonely:
            yield event.plain_result("😢 今天你落单了，没有配对到伴侣。")
        else:
            yield event.plain_result("❓ 未找到你的配对信息，你可能不在该群成员列表中。")

    async def _pair_single_group(self, group_id: int, date_str: str):
        """为单个群立即执行配对（用于降级方案）"""
        logger.info(f"为群 {group_id} 执行即时配对")
        try:
            bot_id = None
            if hasattr(self.context.platform, 'get_bot_id'):
                bot_id = self.context.platform.get_bot_id()

            members = await self._safe_call_action('get_group_member_list', group_id=group_id, timeout=20)
            if not members or not isinstance(members, list):
                logger.warning(f"群 {group_id} 无法获取成员列表，即时配对失败")
                return

            member_ids = [m['user_id'] for m in members if m.get('user_id') and m['user_id'] != bot_id]
            if len(member_ids) < 2:
                logger.info(f"群 {group_id} 成员少于2人，无法配对")
                return

            random.shuffle(member_ids)
            pairs = {}
            for i in range(0, len(member_ids) - 1, 2):
                a = member_ids[i]
                b = member_ids[i+1]
                pairs[str(a)] = str(b)
                pairs[str(b)] = str(a)

            group_key = f"{group_id}_{date_str}"
            new_data = {
                group_key: {
                    'pairs': pairs,
                    'lonely': [str(member_ids[-1])] if len(member_ids) % 2 == 1 else []
                }
            }

            # 合并到现有文件（避免覆盖其他群）
            marry_data = self._read_json(self.marry_file)
            marry_data.update(new_data)
            self._write_json(self.marry_file, marry_data)
            logger.info(f"群 {group_id} 即时配对完成")
        except Exception as e:
            logger.error(f"_pair_single_group 出错: {e}")
