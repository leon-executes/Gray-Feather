"""Draw the application icon."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import struct
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPen, QColor

root = Path(__file__).resolve().parents[1]
image = QImage(256, 256, QImage.Format.Format_ARGB32)
image.fill(QColor('#141a1c'))
painter = QPainter(image)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)
path = QPainterPath(QPointF(68, 195))
path.cubicTo(75, 105, 135, 54, 201, 49)
path.cubicTo(200, 114, 146, 169, 80, 185)
path.lineTo(68, 195)
painter.setBrush(QColor('#c5bd9c'))
painter.setPen(QPen(QColor('#c5bd9c'), 2))
painter.drawPath(path)
painter.setPen(QPen(QColor('#141a1c'), 8))
painter.drawLine(QPointF(65, 201), QPointF(183, 69))
painter.setPen(QPen(QColor('#141a1c'), 4))
for x, y in ((96,160),(121,133),(148,104)):
    painter.drawLine(QPointF(x,y), QPointF(x+29,y+2))
painter.end()
data = QByteArray()
buffer = QBuffer(data)
buffer.open(QIODevice.OpenModeFlag.WriteOnly)
image.save(buffer, 'PNG')
png = bytes(data)
(root / 'grayfeather.png').write_bytes(png)
(root / 'grayfeather.ico').write_bytes(struct.pack('<HHH',0,1,1) + struct.pack('<BBBBHHII',0,0,0,0,1,32,len(png),22) + png)
