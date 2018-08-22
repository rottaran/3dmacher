#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from PyQt5.QtCore import (QObject, pyqtProperty, pyqtSignal, Qt,
    QRect, QPoint, QSize)
from PyQt5.QtWidgets import (QWidget, QPushButton, QToolBar,
    QHBoxLayout, QVBoxLayout, QApplication, QMainWindow, QAction,
    QCheckBox, QRadioButton)
from PyQt5.QtGui import (QPixmap, QImage, QImageReader,
    QPainter, QBrush, QIcon, QColor,
    QTransform)

class ImageState(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sourceFile = None
        self._image = None
        self._transform = QTransform()

    def rotate90(self):
        if self.image == None: return
        self._image = self.image.transformed(QTransform().rotate(90))
        self.changed.emit()

    @pyqtProperty('QImage')
    def image(self): return self._image

    @pyqtProperty('QTransform')
    def transform(self): return self._transform

    @transform.setter
    def transform(self, value):
        self._transform = value
        self.changed.emit()

    @pyqtProperty(str) #'QString'
    def sourceFile(self): return self._sourceFile

    @sourceFile.setter
    def sourceFile(self, value):
        self._sourceFile = value
        p = QImageReader(self._sourceFile)
        if (p.canRead()):
            p.setAutoTransform(True)
            self._image = p.read()
            self._transform = QTransform()
            print("loaded image "+value)
        else:
            self._image = None
        self.changed.emit()

    def paintImage(self, qp, dst):
        if (self.image == None): return
        qp.save()
        qp.setClipRect(dst)
        qp.translate(dst.x()+dst.width()/2, dst.y()+dst.height()/2)
        qp.setTransform(self.transform, True) # combine with image's transform
        qp.scale(dst.width()/self.image.width(), dst.width()/self.image.width())
        qp.translate(-self.image.width()/2, -self.image.height()/2)
        qp.drawImage(0,0, self.image)
        qp.restore()
        #qp.setClipping(False)


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

    def paintImage(self, qp, dst):
        # render left image
        sub = QRect(dst.x(), dst.y(), dst.width()/2, dst.height())
        self.leftState().paintImage(qp, sub)

        # render right image
        sub = QRect(dst.x()+dst.width()/2, dst.y(), dst.width()/2, dst.height())
        self.rightState().paintImage(qp, sub)

    def proposeFilename(self):
        if (self.leftState().image == None or
            self.rightState().image == None):
            return None
        pl = Path(self.leftState().sourceFile)
        pr = Path(self.rightState().sourceFile)
        return str(pl.parent.joinpath(pl.stem+"-"+pr.stem+".jpg"))


class ImageView(QWidget):
    mousePress = pyqtSignal('QMouseEvent')
    mouseMove = pyqtSignal('QMouseEvent')
    mouseRelease = pyqtSignal('QMouseEvent')
    def mousePressEvent(self, m): self.mousePress.emit(m)
    def mouseMoveEvent(self, m): self.mouseMove.emit(m)
    def mouseReleaseEvent(self, m): self.mouseRelease.emit(m)

    def __init__(self, state, config, right, parent=None):
        super().__init__(parent)
        self.right = right
        self.state = state
        self.config = config
        # self.setFixedSize(self.config.aspectRatio.width()*50/2,
        #         self.config.aspectRatio.height()*50)
        self.setMinimumSize(self.config.aspectRatio.width()*10/2,
            self.config.aspectRatio.height()*10)
        self.setMaximumSize(self.config.aspectRatio.width()*100/2,
            self.config.aspectRatio.height()*100)
        # self.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.setAcceptDrops(True)
        self.state.changed.connect(self.repaint)

    def sizeHint(self):
        return QSize(self.config.aspectRatio.width()*100/2,
            self.config.aspectRatio.height()*100)

    # def resizeEvent(self, e):
    #     e.accept()
    #     w = self.config.aspectRatio.width()
    #     h = self.config.aspectRatio.height()*2
    #     if e.size().width() > w*e.size().height()/h:
    #         self.resize(w*e.size().height()/h, e.size().height())
    #     else:
    #         self.resize(e.size().width(), h*e.size().width()/w)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and e.mimeData().urls()[0].isLocalFile():
            e.accept()
        else:
            e.ignore()

    def dropEvent(self, e):
        # could use e.pos() to see if it is in the left or right half
        self.state.sourceFile = e.mimeData().urls()[0].toLocalFile()

    def imgRect(self):
        aw = self.config.aspectRatio.width()
        ah = self.config.aspectRatio.height()*2
        x = 0
        if self.width() > aw*self.height()/ah:
            w = aw*self.height()/ah
            h = self.height()
            if not self.right: x = self.width()-w
        else:
            w = self.width()
            h = ah*self.width()/aw
        return QRect(x,0,w,h)

    def paintEvent(self, event):
        dst = self.imgRect()

        qp = QPainter()
        qp.begin(self)

        brush = QBrush(Qt.SolidPattern)
        brush.setColor(Qt.white)
        qp.setBrush(brush)
        qp.drawRect(dst)

        brush = QBrush(Qt.DiagCrossPattern)
        brush.setColor(Qt.black)
        qp.setBrush(brush)
        qp.drawRect(dst)
        self.state.paintImage(qp, dst)

        qp.setPen(QColor(255,255,255,150))
        qp.drawLine(dst.x()+dst.width()/3,dst.y()+0,
            dst.x()+dst.width()/3,dst.y()+dst.height())
        qp.drawLine(dst.x()+dst.width()/2,dst.y()+0,
            dst.x()+dst.width()/2,dst.y()+dst.height())
        qp.drawLine(dst.x()+dst.width()*2/3,dst.y()+0,
            dst.x()+dst.width()*2/3,dst.y()+dst.height())
        qp.drawLine(dst.x()+0,dst.y()+dst.height()/3,
            dst.x()+dst.width(),dst.y()+dst.height()/3)
        qp.drawLine(dst.x()+0,dst.y()+dst.height()/2,
            dst.x()+dst.width(),dst.y()+dst.height()/2)
        qp.drawLine(dst.x()+0,dst.y()+dst.height()*2/3,
            dst.x()+dst.width(),dst.y()+dst.height()*2/3)
        qp.end()


class ImageWindow(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config

        self.setWindowTitle('3D Vorschau')

        vbox = QVBoxLayout()

        # buttons for global operations, modes
        save = QPushButton("Speichern")
        save.clicked.connect(self.saveTriggered)
        rotleft = QPushButton("Linkes drehen")
        rotleft.clicked.connect(self.config.leftState().rotate90)
        rotright = QPushButton("Rechtes drehen")
        rotright.clicked.connect(self.config.rightState().rotate90)
        self.linkedBtn = QCheckBox("verbunden")
        self.rotateBtn = QRadioButton("drehen+skalieren")
        self.moveBtn = QRadioButton("schieben")

        tb = QHBoxLayout()
        tb.addWidget(save)
        #tb.addWidget(rotleft)
        #tb.addWidget(rotright)
        tb.addWidget(self.linkedBtn)
        tb.addWidget(self.rotateBtn)
        tb.addWidget(self.moveBtn)
        vbox.addLayout(tb)
        self.rotateBtn.setChecked(True)

        # the views to the left and right image
        self.leftImage = ImageView(self.config.leftState(), self.config, False)
        self.rightImage = ImageView(self.config.rightState(), self.config, True)
        imgbox = QHBoxLayout()
        imgbox.setSpacing(0)
        imgbox.addStretch(1)
        imgbox.addWidget(self.leftImage)
        imgbox.addWidget(self.rightImage)
        imgbox.addStretch(1)

        vbox.addLayout(imgbox)
        self.setLayout(vbox)

        self.leftImage.mousePress.connect(self.mousePressL)
        self.leftImage.mouseMove.connect(self.mouseMove)
        self.rightImage.mousePress.connect(self.mousePressR)
        self.rightImage.mouseMove.connect(self.mouseMove)

    def computeRotateScale(self, start, end):
        try:
            p1 = start - self._mouseCenter
            p2 = end - self._mouseCenter
            s = float(p1.y()*p2.x()-p1.x()*p2.y())/float(p1.x()*p1.x()+p1.y()*p1.y())
            c = (p2.y()+p1.x()*s)/p1.y()
            return QTransform(c,-s,s,c,0,0)
        except ZeroDivisionError:
            return QTransform()

    def computeMove(self, start, end):
        try:
            m = end-start
            return QTransform(1,0,0,1,m.x(),m.y())
        except ZeroDivisionError:
            return QTransform()

    def mousePressL(self, m):
        self._mouseCenter = self.leftImage.imgRect().center()
        self.mousePress(m,0)

    def mousePressR(self, m):
        self._mouseCenter = self.rightImage.imgRect().center()
        self.mousePress(m,1)

    def mousePress(self, m, side):
        self._mouseStart = m.pos()
        self._mouseSide = side
        self._leftTransform = self.config.leftState().transform
        self._rightTransform = self.config.rightState().transform

    def mouseMove(self, m):
        self._mouseEnd = m.pos()
        if self.rotateBtn.isChecked():
            transform = self.computeRotateScale(self._mouseStart, self._mouseEnd)
        elif self.moveBtn.isChecked():
            transform = self.computeMove(self._mouseStart, self._mouseEnd)
        if (self._mouseSide==0 or self.linkedBtn.isChecked()):
            self.config.leftState().transform = self._leftTransform * transform
        if (self._mouseSide==1 or self.linkedBtn.isChecked()):
            self.config.rightState().transform = self._rightTransform * transform


    def saveTriggered(self):
        dstFile = self.config.proposeFilename()
        if dstFile == None: return
        print("saving in "+dstFile)

        # create an image for the final output
        img = QImage(self.config.saveSize, QImage.Format_RGB32)
        qp = QPainter(img)

        # black background and then the images
        dst = QRect(0,0,img.width(), img.height())
        brush = QBrush(Qt.SolidPattern)
        brush.setColor(Qt.black)
        qp.setBrush(brush)
        qp.drawRect(dst)
        self.config.paintImage(qp, dst)

        qp.end()
        img.save(dstFile)


if __name__ == '__main__':

    app = QApplication(sys.argv)
    config = GlobalConfig()
    iw = ImageWindow(config)
    iw.show()

    sys.exit(app.exec_())
