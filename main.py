import random
import json
import os
from datetime import date
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

@register("astrbot_plugin_win_only", "你的名字", "仅提供win指令，每日随机生成win值", "1.0.0")
class WinOnlyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 数据存储路径：data/plugins/astrbot_plugin_win_only/
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
        except Exception:
            return {}

    def _write_json(self, file_path: str, data: dict) -> None:
        """将数据写入 JSON 文件"""
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            # 可记录日志，此处忽略
            pass

    @filter.command("win")
    async def win(self, event: AstrMessageEvent):
        """获取今日的 win 值"""
        user_id = event.get_sender_id()
        today_str = str(date.today())

        win_data = self._read_json(self.win_file)

        # 检查用户今天是否已有记录
        if user_id in win_data and win_data[user_id].get('date') == today_str:
            win_value = win_data[user_id]['value']
            yield event.plain_result(f"你今天已经赢过了，win值是：{win_value}")
        else:
            # 生成 1-100 的随机数
            new_win = random.randint(1, 100)
            win_data[user_id] = {
                'date': today_str,
                'value': new_win
            }
            self._write_json(self.win_file, win_data)
            yield event.plain_result(f"✨ 今日win值已生成：{new_win}")
