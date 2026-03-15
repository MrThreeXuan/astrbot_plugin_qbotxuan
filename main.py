import random
import json
import os
import statistics
from datetime import date
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain

@register("astrbot_plugin_win_only", "你的名字", "仅提供win指令，每日随机生成win值", "1.0.0")
class WinOnlyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 持久化数据存储于data目录下，防止更新/重装插件时数据被覆盖 [citation:3]
        plugin_dir = os.path.dirname(__file__)
        self.data_dir = os.path.join(plugin_dir, '../../data/astrbot_plugin_win_only')
        os.makedirs(self.data_dir, exist_ok=True)
        self.win_file = os.path.join(self.data_dir, 'win_data.json')

    def _read_json(self, file_path: str) -> dict:
        """读取 JSON 文件，如果不存在则返回空字典"""
        if not os.path.exists(file_path):
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取JSON文件失败: {e}")
            return {}

    def _write_json(self, file_path: str, data: dict) -> None:
        """将数据写入 JSON 文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"写入JSON文件失败: {e}")

    @filter.command("win")
    async def win(self, event: AstrMessageEvent):
        """获取今日的 win 值
        
        根据当前日期判断，同一天内同一用户多次发送 win 只会返回首次生成的值。
        """
        user_id = event.get_sender_id()
        # 获取群ID，如果是私聊则为空字符串 [citation:1]
        group_id = event.message_obj.group_id if hasattr(event.message_obj, 'group_id') else ""
        today_str = str(date.today())

        win_data = self._read_json(self.win_file)

        # 检查用户今天是否已有记录（按用户ID区分，跨群统一）
        if user_id in win_data and win_data[user_id].get('date') == today_str:
            win_value = win_data[user_id]['value']
            yield event.plain_result(f"你今天已经赢过了，win值是：{win_value}")
        else:
            # 生成 1-100 的随机数
            new_win = random.randint(1, 100)
            # 存储用户信息，包括群ID以便后续群内排序 [citation:5]
            win_data[user_id] = {
                'date': today_str,
                'value': new_win,
                'group_id': group_id,  # 记录用户所在的群
                'user_name': event.get_sender_name()  # 记录用户昵称
            }
            self._write_json(self.win_file, win_data)
            yield event.plain_result(f"✨ 今日win值已生成：{new_win}")

    @filter.command("rank")
    async def rank(self, event: AstrMessageEvent):
        """对当前群今日发送win指令的人进行赢值排序
        
        输出格式：
        今日群内有X人赢了，赢值排序：
        1. 【用户群昵称】【空格】【赢值】
        ...
        最后输出平均数、中位数、方差
        """
        # 获取当前群ID，如果是私聊则无法使用rank指令
        group_id = event.message_obj.group_id if hasattr(event.message_obj, 'group_id') else ""
        
        if not group_id:
            yield event.plain_result("该指令只能在群聊中使用")
            return

        today_str = str(date.today())
        win_data = self._read_json(self.win_file)

        # 筛选今日在当前群内有记录的用户 [citation:5]
        group_users = []
        for user_id, data in win_data.items():
            if data.get('date') == today_str and data.get('group_id') == group_id:
                # 获取用户当前群昵称（可能已更改），优先使用消息事件中获取的最新昵称
                # 如果无法获取，则使用存储的历史昵称
                try:
                    # 尝试获取发送者的群昵称
                    member_info = await self.context.get_group_member(group_id, user_id)
                    user_name = member_info.get('nickname', '') or member_info.get('card', '') or data.get('user_name', '未知用户')
                except:
                    # 获取失败时使用存储的昵称
                    user_name = data.get('user_name', '未知用户')
                
                group_users.append({
                    'user_id': user_id,
                    'user_name': user_name,
                    'value': data['value']
                })

        if not group_users:
            yield event.plain_result("今日群内还没有人使用过win指令哦~")
            return

        # 按赢值从高到低排序
        group_users.sort(key=lambda x: x['value'], reverse=True)

        # 构建回复消息
        result_msg = f"今日群内有 {len(group_users)} 人赢了，赢值排序：\n"
        for i, user in enumerate(group_users, 1):
            result_msg += f"{i}. {user['user_name']} {user['value']}\n"

        # 计算统计信息 [citation:1]
        values = [user['value'] for user in group_users]
        
        # 平均数
        mean_value = statistics.mean(values)
        
        # 中位数
        median_value = statistics.median(values)
        
        # 方差（使用总体方差，即除以n）
        variance_value = statistics.pvariance(values) if len(values) > 1 else 0

        # 格式化统计信息，保留两位小数
        result_msg += f"\n📊 统计信息：\n"
        result_msg += f"平均值：{mean_value:.2f}\n"
        result_msg += f"中位数：{median_value:.2f}\n"
        result_msg += f"方差：{variance_value:.2f}"

        yield event.plain_result(result_msg)
