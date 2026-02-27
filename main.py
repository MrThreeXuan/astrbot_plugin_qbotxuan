import random
import json
import os
from datetime import date
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

@register("astrbot_plugin_qqfun", "你的名字", "实现win和marry功能的插件", "1.0.0")
class QQFunPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # 数据存储路径：data/plugins/astrbot_plugin_qqfun/
        # 使用 os.path.dirname(__file__) 获取当前文件所在目录
        plugin_dir = os.path.dirname(__file__)
        # 将数据存放在 data 目录下（与插件目录同级的 data/插件名/）
        self.data_dir = os.path.join(plugin_dir, '../../data/astrbot_plugin_qqfun')
        os.makedirs(self.data_dir, exist_ok=True)
        self.win_file = os.path.join(self.data_dir, 'win_data.json')
        self.marry_file = os.path.join(self.data_dir, 'marry_data.json')

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
            # 可以在这里记录日志，但简单忽略
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

    @filter.command("marry")
    async def marry(self, event: AstrMessageEvent):
        """在群内寻找今日的伴侣"""
        # 仅限群聊使用
        group_id = event.get_group_id()
        if not group_id:
            yield event.plain_result("该指令只能在群聊中使用。")
            return

        user_id = event.get_sender_id()
        today_str = str(date.today())
        # 以群组+日期为键，确保不同群组数据隔离，且每日重置
        group_key = f"{group_id}_{today_str}"

        marry_data = self._read_json(self.marry_file)
        if group_key not in marry_data:
            marry_data[group_key] = {'pool': [], 'pairs': {}}

        pool = marry_data[group_key]['pool']
        pairs = marry_data[group_key]['pairs']

        # 1. 检查用户今天是否已经结婚
        if user_id in pairs:
            mate_id = pairs[user_id]
            # 可以尝试获取昵称，这里简单返回 QQ 号
            yield event.plain_result(f"你今天已经和 {mate_id} 结婚了，要幸福哦！")
            return

        # 2. 如果用户已经在等待池中，防止重复入池
        if user_id in pool:
            yield event.plain_result("你已经在等待池里了，请耐心等待下一位有缘人~")
            return

        # 3. 匹配逻辑
        if pool:
            # 从池中取出第一个用户作为配偶
            mate_id = pool.pop(0)
            # 双向记录配对
            pairs[user_id] = mate_id
            pairs[mate_id] = user_id
            self._write_json(self.marry_file, marry_data)

            # 获取发送者的昵称，让消息更友好
            sender_name = event.get_sender_name()
            yield event.plain_result(f"🎉 恭喜 {sender_name} 和 {mate_id} 今日喜结良缘！")
        else:
            # 池为空，将用户加入池中
            pool.append(user_id)
            self._write_json(self.marry_file, marry_data)
            yield event.plain_result("💘 已将你放入等待池，请等待下一位指令使用者与你匹配。")
