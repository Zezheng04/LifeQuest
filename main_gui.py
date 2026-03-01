"""
LifeQuest - PyQt6 游戏风格主界面
新增：四维属性完全自定义(JSON配置)、引入本地自定义WAV音效系统。
"""
import math
import sys
import json
import os
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QSequentialAnimationGroup, 
    QObject, pyqtProperty, QTimer, QPoint, QDate, QUrl
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QProgressBar, QFrame, QScrollArea, QCheckBox, QSplitter, 
    QGridLayout, QPushButton, QDialog, QDialogButtonBox, QFormLayout, 
    QLineEdit, QComboBox, QSpinBox, QMessageBox, QTableWidget, QTableWidgetItem,
    QGraphicsOpacityEffect, QDateEdit, QGroupBox
)
from PyQt6.QtGui import QPainter, QPen, QBrush, QColor, QFont, QPainterPath

# 引入音频模块
from PyQt6.QtMultimedia import QSoundEffect

from database import DatabaseManager
from models import Player, Rival, Quest, QuestStatus, QuestType, QuestAttribute

# ---------- 本地配置系统 ----------
CONFIG_FILE = "config.json"

def load_config():
    default_config = {
        "target_name": "雅思 8.0 竞速对决", 
        "target_date": "2024-12-31",
        "attr1": "听力(感知)",
        "attr2": "阅读(洞察)",
        "attr3": "写作(逻辑)",
        "attr4": "口语(魅力)"
    }
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            # 合并默认配置，防止老版本配置缺失新字段
            for k, v in default_config.items():
                if k not in user_config:
                    user_config[k] = v
            return user_config
    return default_config

def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

# ---------- 音效管理器 ----------
class SoundManager:
    def __init__(self):
        self.sounds = {}
        # 预加载三个核心音效文件
        self._load_sound("success", "success.wav")
        self._load_sound("crit", "crit.wav")
        self._load_sound("fail", "fail.wav")

    def _load_sound(self, name, filename):
        effect = QSoundEffect()
        path = os.path.abspath(filename)
        if os.path.exists(path):
            effect.setSource(QUrl.fromLocalFile(path))
            # 可以通过 effect.setVolume(0.8) 调节音量 (0.0 到 1.0)
            self.sounds[name] = effect
        else:
            self.sounds[name] = None

    def play(self, name):
        effect = self.sounds.get(name)
        if effect:
            effect.play()
        else:
            # 文件不存在时，降级使用系统提示音
            QApplication.beep()

# ---------- 经验条动画辅助 ----------
class ProgressBarAnimator(QObject):
    def __init__(self, bar: QProgressBar, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._bar = bar

    def get_value(self) -> float: return self._value
    def set_value(self, v: float) -> None:
        self._value = v
        self._bar.setValue(int(round(v)))
    value = pyqtProperty(float, get_value, set_value)

# ---------- 漂浮字体特效 ----------
class FloatingText(QLabel):
    def __init__(self, text, start_pos, parent, color="lime", font_size=20):
        super().__init__(text, parent)
        self.setStyleSheet(f"color: {color}; font-size: {font_size}px; font-weight: bold; background: transparent; text-shadow: 2px 2px 4px #000;")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.adjustSize()
        self.move(start_pos.x() - self.width() // 2, start_pos.y() - self.height() // 2)
        self.show()

        self.effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.effect)
        self.anim_group = QSequentialAnimationGroup(self)
        
        anim_pos = QPropertyAnimation(self, b"pos")
        anim_pos.setDuration(1500)
        anim_pos.setStartValue(self.pos())
        anim_pos.setEndValue(QPoint(self.pos().x(), self.pos().y() - 60))
        anim_pos.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        anim_opacity = QPropertyAnimation(self.effect, b"opacity")
        anim_opacity.setDuration(1500)
        anim_opacity.setStartValue(1.0)
        anim_opacity.setEndValue(0.0)

        anim_pos.start(); anim_opacity.start()
        QTimer.singleShot(1600, self.deleteLater)

# ---------- 属性雷达图 ----------
class AttributeRadarWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        # 稍微放大一点最小尺寸，给四周留足空间
        self.setMinimumSize(280, 280)
        self.p_stats = [5.0, 5.0, 5.0, 5.0]
        self.r_stats = [5.0, 5.0, 5.0, 5.0]
        self._max_val = 10.0
        self.attr_labels = ["属性2", "属性4", "属性3", "属性1"]

    def set_attributes(self, p: Player, r: Rival, config: dict):
        # 对应关系: 上(Insight), 右(Charisma), 下(Logic), 左(Perception)
        self.p_stats = [p.insight, p.charisma, p.logic, p.perception]
        self.r_stats = [r.insight, r.charisma, r.logic, r.perception]
        self._max_val = max(10.0, max(self.p_stats), max(self.r_stats)) + 2.0
        
        self.attr_labels = [
            config["attr2"], # 上
            config["attr4"], # 右
            config["attr3"], # 下
            config["attr1"]  # 左
        ]
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2

        # 核心修复 1：把雷达的最大半径缩小，强制给四周边缘留出 45 像素的空间放文字
        r = min(w, h) / 2 - 45

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 核心修复 2：修正顶点角度，标准的上、右、下、左
        angles = [-90, 0, 90, 180]

        def get_pt(radius, angle):
            rad = math.radians(angle)
            return cx + radius * math.cos(rad), cy + radius * math.sin(rad)

        # 1. 画背景网格 (修复断线问题)
        pen_grid = QPen(QColor(60, 80, 70))
        pen_grid.setWidth(1)
        painter.setPen(pen_grid)
        for i in range(1, 5):
            rr = r * i / 4
            path = QPainterPath()
            path.moveTo(*get_pt(rr, angles[0]))
            for ang in angles[1:]:
                path.lineTo(*get_pt(rr, ang))
            path.closeSubpath()
            painter.drawPath(path)

        # 2. 画十字轴线
        for ang in angles:
            px, py = get_pt(r, ang)
            painter.drawLine(int(cx), int(cy), int(px), int(py))

        # 3. 数据多边形生成函数
        def get_data_path(stats):
            path = QPainterPath()
            for i, val in enumerate(stats):
                radius = (val / self._max_val) * r
                px, py = get_pt(radius, angles[i])
                if i == 0: path.moveTo(px, py)
                else: path.lineTo(px, py)
            path.closeSubpath()
            return path

        # 4. 画对手 (红色底层)
        r_path = get_data_path(self.r_stats)
        painter.fillPath(r_path, QBrush(QColor(200, 50, 50, 70)))
        painter.setPen(QPen(QColor(255, 80, 80), 2))
        painter.drawPath(r_path)

        # 5. 画玩家 (绿色表层)
        p_path = get_data_path(self.p_stats)
        painter.fillPath(p_path, QBrush(QColor(0, 180, 120, 100)))
        painter.setPen(QPen(QColor(0, 255, 160), 2))
        painter.drawPath(p_path)

        # 6. 画边缘文字 (核心修复 3：智能对齐防遮挡)
        painter.setPen(QColor(200, 255, 200))
        font = QFont(self.font())
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        metrics = painter.fontMetrics()

        for i, ang in enumerate(angles):
            text = self.attr_labels[i]
            tw = metrics.horizontalAdvance(text)
            th = metrics.height()
            
            # 文字离雷达的最外圈顶点再向外延展 12 像素
            px, py = get_pt(r + 12, ang)

            # 根据文字在四个不同的方向，做对应的居中偏移修正
            if ang == -90:   # 上方文字，水平居中
                px -= tw / 2
            elif ang == 0:   # 右侧文字，垂直居中
                py += th / 3
            elif ang == 90:  # 下方文字，水平居中，并向下让出字高
                px -= tw / 2
                py += th
            elif ang == 180: # 左侧文字，向左让出整个字宽，垂直居中
                px -= tw
                py += th / 3

            painter.drawText(int(px), int(py), text)

# ---------- 全局 QSS 样式 ----------
def get_stylesheet() -> str:
    return """
    QMainWindow, QWidget { background-color: #0d1117; color: #c9d1d9; }
    QMessageBox { background-color: #161b22; }
    QMessageBox QLabel { color: #c9d1d9; font-size: 14px; }
    QMessageBox QPushButton { min-width: 80px; }
    QGroupBox { border: 1px solid #30363d; border-radius: 6px; margin-top: 10px; padding-top: 15px; font-weight: bold; color: #7ee787;}
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px 0 5px; }
    QFrame#statusFrame, QFrame#questFrame, QFrame#attrFrame { background-color: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 8px; }
    QFrame#statusFrame { border: 2px solid #238636; border-radius: 8px; padding: 10px; }
    QLabel#titleLabel { color: #7ee787; font-size: 18px; font-weight: bold; padding: 4px 0; }
    QLabel#levelLabel { color: #7ee787; font-size: 20px; font-weight: bold; }
    QLabel#rivalLabel { color: #f85149; font-size: 20px; font-weight: bold; }
    QLabel#goldLabel { color: #f0d84a; font-size: 16px; font-weight: bold; }
    QProgressBar { border: 1px solid #30363d; border-radius: 6px; text-align: center; background-color: #21262d; min-height: 22px; color: white; font-weight: bold;}
    QProgressBar#playerBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #238636, stop:1 #2ea043); border-radius: 5px; }
    QProgressBar#rivalBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #da3633, stop:1 #f85149); border-radius: 5px; }
    QCheckBox { color: #c9d1d9; font-size: 14px; spacing: 8px; }
    QCheckBox::indicator { width: 20px; height: 20px; border: 2px solid #7ee787; border-radius: 4px; background-color: #21262d; }
    QCheckBox::indicator:checked { background-color: #238636; border-color: #7ee787; }
    QScrollArea { border: none; background-color: transparent; }
    QScrollBar:vertical { background: #21262d; width: 10px; border-radius: 5px; margin: 0; }
    QScrollBar::handle:vertical { background: #388bfd; border-radius: 5px; min-height: 24px; }
    QPushButton { background-color: #21262d; color: #7ee787; border: 1px solid #30363d; border-radius: 6px; padding: 8px 16px; font-weight: bold; }
    QPushButton:hover { background-color: #30363d; border-color: #7ee787; }
    QPushButton:pressed { background-color: #238636; }
    QPushButton#abandonBtn { color: #f85149; border-color: #da3633; }
    QPushButton#abandonBtn:hover { background-color: #da3633; color: white;}
    QPushButton#editBtn { background-color: transparent; border: none; font-size: 16px; padding: 0;}
    QPushButton#editBtn:hover { background-color: #30363d; border-radius: 4px;}
    QLineEdit, QComboBox, QSpinBox, QDateEdit { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; border-radius: 4px; padding: 6px; min-height: 20px; }
    QTableWidget { background-color: #161b22; color: #c9d1d9; gridline-color: #30363d; }
    QHeaderView::section { background-color: #21262d; color: white; border: 1px solid #30363d; padding: 4px;}
    """

# ---------- 目标设置对话框 (包含自定义属性) ----------
class TargetSettingsDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎯 系统配置")
        self.setStyleSheet(get_stylesheet())
        layout = QVBoxLayout(self)
        
        # 1. 主线目标设置
        group_target = QGroupBox("竞速目标设定")
        form1 = QFormLayout(group_target)
        self.name_edit = QLineEdit(config["target_name"])
        form1.addRow("大目标名称:", self.name_edit)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.fromString(config["target_date"], "yyyy-MM-dd"))
        form1.addRow("决战日期:", self.date_edit)
        layout.addWidget(group_target)

        # 2. 四维属性名称自定义
        group_attr = QGroupBox("四维成长体系自定义")
        form2 = QFormLayout(group_attr)
        self.attr1_edit = QLineEdit(config["attr1"])
        self.attr2_edit = QLineEdit(config["attr2"])
        self.attr3_edit = QLineEdit(config["attr3"])
        self.attr4_edit = QLineEdit(config["attr4"])
        form2.addRow("属性槽 1:", self.attr1_edit)
        form2.addRow("属性槽 2:", self.attr2_edit)
        form2.addRow("属性槽 3:", self.attr3_edit)
        form2.addRow("属性槽 4:", self.attr4_edit)
        layout.addWidget(group_attr)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        
    def get_data(self):
        return {
            "target_name": self.name_edit.text(),
            "target_date": self.date_edit.date().toString("yyyy-MM-dd"),
            "attr1": self.attr1_edit.text(),
            "attr2": self.attr2_edit.text(),
            "attr3": self.attr3_edit.text(),
            "attr4": self.attr4_edit.text()
        }

# ---------- 历史卷宗对话框 ----------
class QuestHistoryDialog(QDialog):
    def __init__(self, db: DatabaseManager, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📜 历史卷宗")
        self.resize(550, 350)
        self.setStyleSheet(get_stylesheet())
        layout = QVBoxLayout(self)
        table = QTableWidget()
        quests = db.list_quests(status=QuestStatus.COMPLETE)
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["完成时间", "任务名", "类型", "提升属性"])
        table.setRowCount(len(quests))
        
        # 属性名称映射
        attr_map = {
            QuestAttribute.PERCEPTION.value: config["attr1"],
            QuestAttribute.INSIGHT.value: config["attr2"],
            QuestAttribute.LOGIC.value: config["attr3"],
            QuestAttribute.CHARISMA.value: config["attr4"],
        }
        
        for i, q in enumerate(reversed(quests)):
            table.setItem(i, 0, QTableWidgetItem(q.completed_at or "未知"))
            table.setItem(i, 1, QTableWidgetItem(q.name))
            table.setItem(i, 2, QTableWidgetItem(q.quest_type.value))
            table.setItem(i, 3, QTableWidgetItem(attr_map.get(q.attribute.value, q.attribute.value)))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(table)

# ---------- 添加任务对话框 ----------
class AddQuestDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("添加任务")
        self.setMinimumWidth(360)
        self.setStyleSheet(get_stylesheet())
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(); self.name_edit.setPlaceholderText("例如：背诵20个单词")
        form.addRow("任务名称", self.name_edit)
        self.desc_edit = QLineEdit(); self.desc_edit.setPlaceholderText("任务描述")
        form.addRow("描述", self.desc_edit)
        self.type_combo = QComboBox(); self.type_combo.addItems([QuestType.DAILY.value, QuestType.MAIN.value])
        form.addRow("类型", self.type_combo)
        
        # 动态加载自定义属性名
        self.attr_combo = QComboBox()
        self.attr_combo.addItems([config["attr1"], config["attr2"], config["attr3"], config["attr4"]])
        form.addRow("对应属性", self.attr_combo)
        
        self.difficulty_spin = QSpinBox(); self.difficulty_spin.setRange(1, 5); self.difficulty_spin.setValue(2)
        form.addRow("难度 (1-5)", self.difficulty_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._try_accept); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _try_accept(self) -> None:
        if self.name_edit.text().strip(): self.accept()

    def get_quest_data(self):
        name = self.name_edit.text().strip()
        desc = self.desc_edit.text().strip()
        if not name: return None
        
        # 根据选择的文本反推对应的内部属性槽
        selected_text = self.attr_combo.currentText()
        if selected_text == self.config["attr1"]: attr = QuestAttribute.PERCEPTION
        elif selected_text == self.config["attr2"]: attr = QuestAttribute.INSIGHT
        elif selected_text == self.config["attr3"]: attr = QuestAttribute.LOGIC
        else: attr = QuestAttribute.CHARISMA
            
        qt = QuestType.DAILY if self.type_combo.currentText() == QuestType.DAILY.value else QuestType.MAIN
        diff = self.difficulty_spin.value()
        return (name, desc or name, qt, attr, diff)


# ---------- 主窗口 ----------
class MainWindow(QMainWindow):
    def __init__(self, db_path: str = "lifequest.db"):
        super().__init__()
        self.db = DatabaseManager(db_path)
        self.db.create_tables()
        self.db.init_player_if_missing()
        
        self.config = load_config()
        self.sfx = SoundManager() # 初始化自定义音效

        self._animator: Optional[ProgressBarAnimator] = None
        self._anim_group: Optional[QSequentialAnimationGroup] = None

        self.setWindowTitle("LifeQuest — 目标竞速篇")
        self.setMinimumSize(950, 650)
        self.resize(1050, 750)
        self.setStyleSheet(get_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # ---------- 顶部竞速状态栏 ----------
        status_frame = QFrame(); status_frame.setObjectName("statusFrame")
        status_layout = QVBoxLayout(status_frame)

        title_layout = QHBoxLayout()
        self.target_title_label = QLabel(f"🏁 {self.config['target_name']}")
        self.target_title_label.setStyleSheet("color: #7ee787; font-size:18px; font-weight:bold;")
        
        edit_btn = QPushButton("⚙️"); edit_btn.setObjectName("editBtn"); edit_btn.setFixedSize(30, 30)
        edit_btn.clicked.connect(self._open_settings)
        title_layout.addWidget(self.target_title_label); title_layout.addWidget(edit_btn); title_layout.addStretch()
        
        self.countdown_label = QLabel("距目标还有: 计算中...")
        self.countdown_label.setStyleSheet("color: #ff7b72; font-size:18px; font-weight:bold;")
        title_layout.addWidget(self.countdown_label)
        status_layout.addLayout(title_layout)

        p_layout = QHBoxLayout()
        self.level_label = QLabel("你 Lv.1"); self.level_label.setObjectName("levelLabel")
        self.xp_bar = QProgressBar(); self.xp_bar.setObjectName("playerBar"); self.xp_bar.setFormat("你的进度: %v / %m")
        self.gold_label = QLabel("🪙 0"); self.gold_label.setObjectName("goldLabel")
        p_layout.addWidget(self.level_label); p_layout.addWidget(self.xp_bar, 1); p_layout.addWidget(self.gold_label)
        status_layout.addLayout(p_layout)

        r_layout = QHBoxLayout()
        self.rival_lvl_label = QLabel("敌 Lv.1"); self.rival_lvl_label.setObjectName("rivalLabel")
        self.rival_bar = QProgressBar(); self.rival_bar.setObjectName("rivalBar"); self.rival_bar.setFormat("卷王进度: %v / %m")
        r_layout.addWidget(self.rival_lvl_label); r_layout.addWidget(self.rival_bar, 1); r_layout.addWidget(QLabel("          "))
        status_layout.addLayout(r_layout)
        layout.addWidget(status_frame)

        # ---------- 下方两列 ----------
        splitter = QSplitter(Qt.Orientation.Horizontal)

        quest_frame = QFrame(); quest_frame.setObjectName("questFrame")
        quest_layout = QVBoxLayout(quest_frame)
        quest_title = QLabel("📜 任务板 · Quest Board"); quest_title.setObjectName("titleLabel"); quest_layout.addWidget(quest_title)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("➕ 添加任务"); add_btn.clicked.connect(self._on_add_quest)
        hist_btn = QPushButton("📜 历史卷宗"); hist_btn.clicked.connect(lambda: QuestHistoryDialog(self.db, self.config, self).exec())
        btn_layout.addWidget(add_btn); btn_layout.addWidget(hist_btn)
        quest_layout.addLayout(btn_layout)

        self.quest_scroll = QScrollArea(); self.quest_scroll.setWidgetResizable(True)
        self.quest_widget = QWidget(); self._quest_list_layout = QVBoxLayout(self.quest_widget); self._quest_list_layout.setContentsMargins(0, 0, 0, 0)
        self.quest_scroll.setWidget(self.quest_widget); quest_layout.addWidget(self.quest_scroll)
        splitter.addWidget(quest_frame)

        attr_frame = QFrame(); attr_frame.setObjectName("attrFrame")
        attr_layout = QVBoxLayout(attr_frame)
        attr_title = QLabel("⚔ 属性 · Attributes"); attr_title.setObjectName("titleLabel"); attr_layout.addWidget(attr_title)

        self.radar = AttributeRadarWidget()
        attr_layout.addWidget(self.radar, 0, Qt.AlignmentFlag.AlignCenter)

        self.attr_grid = QGridLayout()
        self.attr1_label = QLabel(f"{self.config['attr1']}: 5.0")
        self.attr2_label = QLabel(f"{self.config['attr2']}: 5.0")
        self.attr3_label = QLabel(f"{self.config['attr3']}: 5.0")
        self.attr4_label = QLabel(f"{self.config['attr4']}: 5.0")
        self.attr_grid.addWidget(self.attr1_label, 0, 0)
        self.attr_grid.addWidget(self.attr2_label, 0, 1)
        self.attr_grid.addWidget(self.attr3_label, 1, 0)
        self.attr_grid.addWidget(self.attr4_label, 1, 1)
        attr_layout.addLayout(self.attr_grid)
        splitter.addWidget(attr_frame)

        splitter.setSizes([550, 450])
        layout.addWidget(splitter, 1)

        self._quest_checkboxes = {}
        self._refresh_ui()

    def _open_settings(self):
        dialog = TargetSettingsDialog(self.config, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_data = dialog.get_data()
            self.config.update(new_data)
            save_config(self.config)
            self._refresh_target_ui()
            self._refresh_stats()

    def _refresh_target_ui(self):
        self.target_title_label.setText(f"🏁 {self.config['target_name']}")
        try:
            target_date = datetime.strptime(self.config["target_date"], "%Y-%m-%d")
            days_left = (target_date - datetime.now()).days
            if days_left < 0: self.countdown_label.setText("决战已至！")
            else: self.countdown_label.setText(f"距目标还有: {days_left} 天")
        except:
            self.countdown_label.setText("日期格式错误")

    def _refresh_ui(self) -> None:
        self._refresh_target_ui()
        self._refresh_stats()
        self._refresh_quest_list()

    def _refresh_stats(self) -> None:
        p = self.db.get_player(); r = self.db.get_rival()
        if not p or not r: return
        self.level_label.setText(f"你 Lv.{p.level}")
        self.xp_bar.setMaximum(p.next_level_xp); self.xp_bar.setValue(p.xp)
        self.gold_label.setText(f"🪙 {p.gold}")
        self.rival_lvl_label.setText(f"敌 Lv.{r.level}")
        self.rival_bar.setMaximum(r.next_level_xp); self.rival_bar.setValue(r.xp)
        
        self.radar.set_attributes(p, r, self.config)
        self.attr1_label.setText(f"{self.config['attr1']}: {p.perception:.1f}")
        self.attr2_label.setText(f"{self.config['attr2']}: {p.insight:.1f}")
        self.attr3_label.setText(f"{self.config['attr3']}: {p.logic:.1f}")
        self.attr4_label.setText(f"{self.config['attr4']}: {p.charisma:.1f}")

    def _refresh_quest_list(self) -> None:
        while self._quest_list_layout.count():
            item = self._quest_list_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        self._quest_checkboxes.clear()
        quests = self.db.list_quests(status=QuestStatus.INCOMPLETE)
        for q in quests:
            row = QWidget(); row_layout = QHBoxLayout(row); row_layout.setContentsMargins(0, 4, 0, 4)
            cb = QCheckBox(f"[{q.quest_type.value}] {q.name}")
            cb.setToolTip(q.description)
            cb.setProperty("quest", q)
            cb.stateChanged.connect(self._on_quest_toggled)
            row_layout.addWidget(cb, 1)
            abandon_btn = QPushButton("放弃")
            abandon_btn.setObjectName("abandonBtn")
            abandon_btn.setProperty("quest", q)
            abandon_btn.clicked.connect(self._on_abandon_quest)
            row_layout.addWidget(abandon_btn)
            self._quest_list_layout.addWidget(row)
            self._quest_checkboxes[q.id] = row
        self._quest_list_layout.addStretch()

    def shake_window(self):
        anim = QPropertyAnimation(self, b"pos"); anim.setDuration(300); pos = self.pos()
        anim.setKeyValueAt(0, pos); anim.setKeyValueAt(0.25, pos + QPoint(-10, 5))
        anim.setKeyValueAt(0.5, pos + QPoint(10, -5)); anim.setKeyValueAt(0.75, pos + QPoint(-5, 10))
        anim.setKeyValueAt(1, pos); anim.start()
        self._shake_anim = anim 

    def get_center_pos(self):
        return QPoint(self.width() // 2, self.height() // 3)

    def _on_quest_toggled(self, state: int) -> None:
        if state != Qt.CheckState.Checked.value: return
        sender = self.sender(); q = sender.property("quest")
        pos = self.get_center_pos() 
        player_before = self.db.get_player()
        
        p_after, gained_xp, gained_gold = self.db.complete_quest(q.id)
        if not p_after:
            sender.setCheckState(Qt.CheckState.Unchecked)
            return
            
        # 播放自定义音效，暴击使用 'crit'，普通使用 'success'
        if q.difficulty >= 4 or q.quest_type == QuestType.MAIN:
            self.sfx.play("crit")
            self.shake_window()
            FloatingText("💥 暴击成长！", pos + QPoint(0, 30), self, "#f0d84a", font_size=28)
        else:
            self.sfx.play("success")
            
        FloatingText(f"✨ +{gained_xp} XP | 🪙 +{gained_gold}", pos, self, "lime", font_size=24)
            
        self._play_xp_animation(player_before, p_after)
        self._refresh_stats()
        self._refresh_quest_list()

    def _play_xp_animation(self, before: Player, after: Player) -> None:
        if self._anim_group and self._anim_group.state() == QPropertyAnimation.State.Running:
            self._anim_group.stop()
        self.xp_bar.setMaximum(before.next_level_xp); self.xp_bar.setValue(before.xp)
        self._animator = ProgressBarAnimator(self.xp_bar, self)
        group = QSequentialAnimationGroup(self)
        if after.level > before.level:
            anim1 = QPropertyAnimation(self._animator, b"value"); anim1.setDuration(500); anim1.setStartValue(float(before.xp)); anim1.setEndValue(float(before.next_level_xp)); anim1.setEasingCurve(QEasingCurve.Type.OutCubic); group.addAnimation(anim1)
            anim2 = QPropertyAnimation(self._animator, b"value"); anim2.setDuration(400); anim2.setStartValue(0.0); anim2.setEndValue(float(after.xp)); anim2.setEasingCurve(QEasingCurve.Type.OutCubic); group.addAnimation(anim2)
            def on_first_finished():
                self.xp_bar.setMaximum(after.next_level_xp); self.xp_bar.setValue(0); self._animator.set_value(0)
            group.animationAt(0).finished.connect(on_first_finished)
        else:
            anim = QPropertyAnimation(self._animator, b"value"); anim.setDuration(600); anim.setStartValue(float(before.xp)); anim.setEndValue(float(after.xp)); anim.setEasingCurve(QEasingCurve.Type.OutCubic); group.addAnimation(anim)
        self._anim_group = group; group.start()

    def _on_add_quest(self) -> None:
        dialog = AddQuestDialog(self.config, self)
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        data = dialog.get_quest_data()
        if not data: return
        name, desc, qt, attr, diff = data
        q = Quest(name=name, description=desc, quest_type=qt, attribute=attr, difficulty=diff)
        self.db.insert_quest(q)
        self._refresh_quest_list()

    def _on_abandon_quest(self) -> None:
        q = self.sender().property("quest")
        pos = self.get_center_pos()
        
        penalty_gold = q.difficulty * 5
        rival_gain = q.difficulty * 10
        
        reply = QMessageBox.warning(
            self, "⚠️ 严重警告",
            f"确认放弃任务【{q.name}】？\n\n💸 违约惩罚: 扣除 {penalty_gold} 金币\n😈 致命打击: 你的影子对手将趁机白嫖 {rival_gain} 点经验！",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.abandon_quest(q.id)
            # 播放自定义放弃音效
            self.sfx.play("fail")
            FloatingText(f"💔 -{penalty_gold} 金币 | 😈 对手 +{rival_gain} XP", pos, self, "#f85149", font_size=24)
            self._refresh_ui()

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()