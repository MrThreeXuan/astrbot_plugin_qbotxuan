import random
import json
import os
import asyncio
from datetime import date, datetime
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

@register("astrbot_plugin_qqfun", "你的名字", "实现win和自动marry功能的插件", "1.0.0")
class QQFunPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 数据存储路径
        plugin_dir = os.path.dirname(__file__)
        self.data_dir = os.path.join(plugin_dir, '../../data/astrbot_plugin_qqfun')
        os.makedirs(self.data_dir, exist_ok=True)
        self.win_file = os.path.join(self.data_dir, 'win_data.json')
        self.marry_file = os.path.join(self.data_dir, 'marry_data.json')

    # ---------- 辅助方法 ----------
    def _read_json(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_json(self, file_path: str, data: dict) -> None:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入JSON文件失败: {e}")

    # ---------- win 指令（保持不变）----------
    @filter.command("win")
    async def win(self, event: AstrMessageEvent):
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

    # ---------- 定时任务：每天0点自动为所有群配对 ----------
    @filter.schedule(cron="0 0 * * *")  # 每天0点执行
    async def auto_marry(self):
        """自动读取所有群成员列表并随机配对"""
        logger.info("开始执行每日自动marry配对...")
        # 获取机器人当前登录的QQ号（用于排除自己）
        bot_id = self.context.platform.get_bot_id() if hasattr(self.context.platform, 'get_bot_id') else None
        # 获取机器人加入的所有群列表
        groups = await self._get_group_list()
        if not groups:
            logger.warning("未获取到任何群列表，无法执行配对")
            return

        today_str = str(date.today())
        new_marry_data = {}

        for group in groups:
            group_id = group['group_id']
            # 获取该群所有成员
            members = await self._get_group_member_list(group_id)
            if not members:
                continue
            # 提取成员QQ号，排除机器人自己（如果有）
            member_ids = [m['user_id'] for m in members if m['user_id'] != bot_id]
            if len(member_ids) < 2:
                logger.info(f"群 {group_id} 成员少于2人，跳过配对")
                continue

            # 随机打乱
            random.shuffle(member_ids)
            pairs = {}
            # 两两配对
            for i in range(0, len(member_ids) - 1, 2):
                a = member_ids[i]
                b = member_ids[i+1]
                pairs[str(a)] = str(b)
                pairs[str(b)] = str(a)
            # 如果成员数为奇数，最后一个落单，不配对
            # 存储时使用群+日期作为键
            group_key = f"{group_id}_{today_str}"
            new_marry_data[group_key] = {
                'pairs': pairs,
                'lonely': [str(member_ids[-1])] if len(member_ids) % 2 == 1 else []
            }
            logger.info(f"群 {group_id} 配对完成，共 {len(pairs)//2} 对，落单 {len(new_marry_data[group_key]['lonely'])} 人")

        # 保存新配对数据
        self._write_json(self.marry_file, new_marry_data)
        logger.info("每日自动marry配对完成")

    # ---------- 获取群列表 ----------
    async def _get_group_list(self):
        """通过平台API获取机器人加入的所有群列表"""
        try:
            # 调用 OneBot API get_group_list
            result = await self.context.platform.call_action('get_group_list')
            if result and isinstance(result, list):
                return result
            else:
                logger.error(f"获取群列表失败: {result}")
                return []
        except Exception as e:
            logger.error(f"调用get_group_list异常: {e}")
            return []

    # ---------- 获取群成员列表 ----------
    async def _get_group_member_list(self, group_id: int):
        """获取指定群的所有成员列表"""
        try:
            result = await self.context.platform.call_action('get_group_member_list', group_id=group_id)
            if result and isinstance(result, list):
                return result
            else:
                logger.error(f"获取群 {group_id} 成员列表失败: {result}")
                return []
        except Exception as e:
            logger.error(f"调用get_group_member_list异常: {e}")
            return []

    # ---------- marry 指令（查询今日伴侣）----------
    @filter.command("marry")
    async def query_marry(self, event: AstrMessageEvent):
        """查询自己今日的配对结果"""
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群聊中使用。")
            return

        user_id = event.get_sender_id()
        today_str = str(date.today())
        group_key = f"{group_id}_{today_str}"

        marry_data = self._read_json(self.marry_file)
        if group_key not in marry_data:
            # 可能是定时任务尚未执行，或者当日无配对数据
            yield event.plain_result("今天还没有配对数据，请稍后再试或联系管理员检查定时任务。")
            return

        pairs = marry_data[group_key].get('pairs', {})
        lonely = marry_data[group_key].get('lonely', [])

        if str(user_id) in pairs:
            mate_id = pairs[str(user_id)]
            # 尝试获取昵称，如果没有则用QQ号
            try:
                member_info = await self._get_group_member_info(group_id, mate_id)
                mate_name = member_info.get('nickname') or member_info.get('card') or mate_id
            except:
                mate_name = mate_id
            yield event.plain_result(f"💑 你今天和 {mate_name} 是伴侣哦！")
        elif str(user_id) in lonely:
            yield event.plain_result("😢 今天你落单了，没有配对到伴侣。")
        else:
            yield event.plain_result("❓ 未找到你的配对信息，你可能不在该群成员列表中。")

    # ---------- 获取单个群成员信息（用于显示昵称）----------
    async def _get_group_member_info(self, group_id: int, user_id: str):
        """获取群成员详细信息，返回包含nickname和card的字典"""
        try:
            result = await self.context.platform.call_action('get_group_member_info',
                                                              group_id=group_id,
                                                              user_id=int(user_id))
            return result if result else {}
        except Exception as e:
            logger.error(f"获取群成员信息失败: {e}")
            return {}
