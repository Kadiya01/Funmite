from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from app.ui.theme import C, F, S

class ModernBarChart(QWidget):
    """A beautiful, modern, animated-looking bar chart drawn with QPainter."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = []  # List of tuples: (label, value)
        self._max_val = 0
        self.setMinimumHeight(240)
        
    def set_data(self, data: list[tuple[str, float]]):
        self._data = data
        if data:
            self._max_val = max((v for _, v in data), default=0)
        else:
            self._max_val = 0
        self.update()
        
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        rect = self.rect()
        width = rect.width()
        height = rect.height()
        
        # Margins
        margin_left = 60
        margin_right = 20
        margin_top = 20
        margin_bottom = 40
        
        chart_width = width - margin_left - margin_right
        chart_height = height - margin_top - margin_bottom
        
        # Draw background and grid lines
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(C.CARD))
        painter.drawRoundedRect(rect, 8, 8)
        
        if not self._data or self._max_val == 0:
            painter.setPen(QColor(C.MUTED_FG))
            painter.setFont(QFont("Segoe UI", 12))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "No data available")
            return
            
        # Draw grid lines
        grid_pen = QPen(QColor(C.BORDER_LIGHT))
        grid_pen.setWidth(1)
        painter.setPen(grid_pen)
        
        num_lines = 4
        for i in range(num_lines + 1):
            y = margin_top + chart_height - (i * chart_height / num_lines)
            painter.drawLine(margin_left, int(y), width - margin_right, int(y))
            
            # Y-axis labels
            val = self._max_val * (i / num_lines)
            
            text_rect = QRectF(0, y - 10, margin_left - 10, 20)
            painter.setPen(QColor(C.MUTED_FG))
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            
            # Format value
            if val >= 1000000:
                label_text = f"{val/1000000:.1f}m"
            elif val >= 1000:
                label_text = f"{val/1000:.1f}k"
            else:
                label_text = f"{val:.0f}"
                
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label_text)
            painter.setPen(grid_pen)
            
        # Draw bars
        num_bars = len(self._data)
        bar_spacing = 20
        total_bar_width = chart_width / num_bars if num_bars > 0 else 0
        actual_bar_width = max(min(total_bar_width - bar_spacing, 60), 10)
        
        for i, (label, val) in enumerate(self._data):
            x_center = margin_left + (i + 0.5) * total_bar_width
            x = x_center - actual_bar_width / 2
            
            bar_height = (val / self._max_val) * chart_height if self._max_val > 0 else 0
            y = margin_top + chart_height - bar_height
            
            # Draw bar
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, actual_bar_width, bar_height), 4, 4)
            # Flatten bottom corners
            path.addRect(QRectF(x, y + 4, actual_bar_width, bar_height - 4))
            
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(C.PRIMARY))
            painter.drawPath(path.simplified())
            
            # X-axis label
            label_rect = QRectF(x_center - total_bar_width/2, height - margin_bottom + 10, total_bar_width, 20)
            painter.setPen(QColor(C.FG_SECONDARY))
            
            # Truncate label if too long
            metrics = painter.fontMetrics()
            elided = metrics.elidedText(str(label), Qt.TextElideMode.ElideRight, int(total_bar_width - 4))
            
            painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, elided)
