#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from PyQt5.QtCore import (QObject, pyqtProperty, pyqtSignal, Qt,
    QRect, QPoint, QSize)
from PyQt5.QtWidgets import (QWidget, QPushButton, QToolBar,
    QHBoxLayout, QVBoxLayout, QApplication, QMainWindow, QAction)
from PyQt5.QtGui import (QPixmap, QImage, QPainter, QBrush, QIcon, QColor,
    QTransform)

class ImageState(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sourceFile = None
        self.image = None

    def rotate90(self):
        if self.image == None: return
        self.image = self.image.transformed(QTransform().rotate(90))
        self.changed.emit()

    @pyqtProperty(str) #'QString'
    def sourceFile(self): return self._sourceFile

    #@sourceFile.setter
    def setSourceFile(self, value):
        self._sourceFile = value
        p = QPixmap()
        if (p.load(value)):
            self.image = p
            print("loaded image "+value)
        else:
            self.image = None
        self.changed.emit()


class GlobalConfig(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.left = ImageState(self)
        self.right = ImageState(self)

    @pyqtProperty(QSize)
    def aspectRatio(self): return QSize(16,9)

    @pyqtProperty(QSize)
    def saveSize(self): return self.aspectRatio*120

    def leftState(self): return self.left
    def rightState(self): return self.right


class ImageView(QWidget):
    def __init__(self, state, config, parent=None):
        super().__init__(parent)
        self.state = state
        self.config = config
        self.setFixedSize(self.config.aspectRatio.width()*50/2,
            self.config.aspectRatio.height()*50)
        self.setAcceptDrops(True)
        self.state.changed.connect(self.repaint)

    def mousePressEvent(self, m):
        self._mouseStart = m.pos()
        print("mouse press "+str(self._mouseStart.x())+"x"+str(self._mouseStart.y()))

    def mouseMoveEvent(self, m):
        self._mouseEnd = m.pos()
        print("mouse move "+str(self._mouseEnd.x())+"x"+str(self._mouseEnd.y()))


    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and e.mimeData().urls()[0].isLocalFile():
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        self.state.setSourceFile(e.mimeData().urls()[0].toLocalFile())

    def paintImage(self, qp, dst):
        img = self.state.image
        if (img == None): return
        qp.save()
        qp.setClipRect(dst)
        qp.translate(dst.x()+dst.width()/2, dst.y()+dst.height()/2)
        qp.scale(dst.width()/img.width(), dst.width()/img.width())
        qp.translate(-img.width()/2, -img.height()/2)
        qp.drawPixmap(0,0, img)
        qp.restore()
        qp.setClipping(False)

    def paintEvent(self, event):
        qp = QPainter()
        qp.begin(self)

        brush = QBrush(Qt.SolidPattern)
        brush.setColor(Qt.white)
        qp.setBrush(brush)
        qp.drawRect(0,0,self.width(), self.height())

        brush = QBrush(Qt.DiagCrossPattern)
        brush.setColor(Qt.black)
        qp.setBrush(brush)
        qp.drawRect(0,0,self.width(), self.height())
        self.paintImage(qp, QRect(QPoint(0,0),
            QSize(self.width(), self.height())))

        qp.setPen(QColor(255,255,255,150))
        qp.drawLine(self.width()/3,0,self.width()/3,self.height())
        qp.drawLine(self.width()/2,0,self.width()/2,self.height())
        qp.drawLine(self.width()*2/3,0,self.width()*2/3,self.height())
        qp.drawLine(0,self.height()/3,self.width(),self.height()/3)
        qp.drawLine(0,self.height()/2,self.width(),self.height()/2)
        qp.drawLine(0,self.height()*2/3,self.width(),self.height()*2/3)
        qp.end()


class ImageWindow(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config

        self.setWindowTitle('3D Vorschau')

        vbox = QVBoxLayout()

        save = QPushButton("Speichern")
        save.clicked.connect(self.saveTriggered)
        rotleft = QPushButton("Linkes drehen")
        rotleft.clicked.connect(self.config.leftState().rotate90)
        rotright = QPushButton("Rechtes drehen")
        rotright.clicked.connect(self.config.rightState().rotate90)

        tb = QHBoxLayout()
        tb.addWidget(save)
        tb.addWidget(rotleft)
        tb.addWidget(rotright)
        vbox.addLayout(tb)

        self.leftImage = ImageView(self.config.leftState(), self.config)
        self.rightImage = ImageView(self.config.rightState(), self.config)
        imgbox = QHBoxLayout()
        imgbox.setSpacing(0)
        imgbox.addStretch(1)
        imgbox.addWidget(self.leftImage)
        imgbox.addWidget(self.rightImage)
        imgbox.addStretch(1)

        vbox.addLayout(imgbox)
        self.setLayout(vbox)

    def saveTriggered(self):
        if (self.config.leftState().image == None or
            self.config.rightState().image == None):
            return

        img = QImage(self.config.saveSize, QImage.Format_RGB32)
        qp = QPainter(img)
        dst = QRect(QPoint(0,0),
            QSize(img.width()/2, img.height()))
        self.leftImage.paintImage(qp, dst)
        dst = QRect(QPoint(img.width()/2,0),
            QSize(img.width()/2, img.height()))
        self.rightImage.paintImage(qp, dst)
        qp.end()

        pl = Path(self.config.leftState().sourceFile)
        pr = Path(self.config.rightState().sourceFile)
        dstFile = str(pl.parent.joinpath(pl.stem+"-"+pr.stem+".jpg"))
        print("saving in "+dstFile)
        img.save(dstFile)


if __name__ == '__main__':

    app = QApplication(sys.argv)
    config = GlobalConfig()
    iw = ImageWindow(config)
    iw.show()

    sys.exit(app.exec_())
