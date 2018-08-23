#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from pprint import pprint
import math
from pathlib import Path
from PyQt5.QtCore import (QObject, pyqtProperty, pyqtSignal, Qt,
    QRect, QPoint, QSize, QThread, QMutex, QWaitCondition, QMutexLocker,
    QBuffer, QPointF)
from PyQt5.QtWidgets import (QWidget, QPushButton, QToolBar,
    QHBoxLayout, QVBoxLayout, QApplication, QMainWindow, QAction,
    QCheckBox, QRadioButton, QButtonGroup)
from PyQt5.QtGui import (QPixmap, QImage, QImageReader,
    QPainter, QBrush, QIcon, QColor,
    QTransform)

import cv2
import numpy as np

import os
import shutil
import threading
from http.server import (ThreadingHTTPServer, BaseHTTPRequestHandler)

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
        qp.scale(dst.width(), dst.width())
        qp.setTransform(self.transform, True) # combine with image's transform
        qp.scale(1.0/self.image.width(), 1.0/self.image.width())
        qp.translate(-self.image.width()/2, -self.image.height()/2)
        qp.drawImage(0,0, self.image)
        qp.restore()
        #qp.setClipping(False)


class GlobalConfig(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.left = ImageState(self)
        self.right = ImageState(self)
        self._linked = True
        self._mode = 0

    linkedChanged = pyqtSignal(int)
    @pyqtProperty(int)
    def linked(self): return self._linked
    @linked.setter
    def linked(self, value):
        old = self._linked
        self._linked = value
        if old != value: self.linkedChanged.emit(value)
    def setLinked(self, value): self.linked = (value!=0)

    modeChanged = pyqtSignal(int)
    @pyqtProperty(int)
    def mode(self): return self._mode
    @mode.setter
    def mode(self, value):
        old = self._mode
        self._mode = value
        if old != value: self.modeChanged.emit(value)
    def setMode(self, value): self.mode = value

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

        # draw background
        brush = QBrush(Qt.SolidPattern)
        # brush.setColor(Qt.white)
        brush.setColor(Qt.black)
        qp.setBrush(brush)
        qp.drawRect(dst)
        # brush = QBrush(Qt.DiagCrossPattern)
        # brush.setColor(Qt.black)
        # qp.setBrush(brush)
        # qp.drawRect(dst)

        self.state.paintImage(qp, dst)

        # draw orientation lines
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


class ImageWebserver(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.serveFile("index.html", "text/html; charset=utf-8")
        elif self.path == "/jquery-3.3.1.min.js":
            self.serveFile("jquery-3.3.1.min.js", "text/plain; charset=utf-8")
        elif self.path == "/jquery.fullscreen.min.js":
            self.serveFile("jquery.fullscreen.min.js", "text/plain; charset=utf-8")
        elif self.path.startswith("/img.jpg?"):
            self.serveImage()
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write("<html><head><title>no file</title></head>".encode('utf-8'))
            self.wfile.write("<body><p>Wrong address</p>".encode('utf-8'))
            self.wfile.write(("<p>You accessed path: %s</p>" % self.path).encode('utf-8'))
            self.wfile.write("</body></html>".encode('utf-8'))

    def serveFile(self, file, ctype):
        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.end_headers()
        source = open(Path(sys.argv[0]).parent.joinpath(file), 'rb')
        shutil.copyfileobj(source, self.wfile)

    def serveImage(self):
        self.send_response(200)
        self.send_header("Content-type", "image/jpeg")
        self.end_headers()

        cfg = self.server.appconfig
        # create an image for the final output
        img = QImage(cfg.saveSize, QImage.Format_RGB888)
        qp = QPainter(img)
        # black background and then the images
        dst = QRect(0,0,img.width(), img.height())
        brush = QBrush(Qt.SolidPattern)
        brush.setColor(Qt.black)
        qp.setBrush(brush)
        qp.drawRect(dst)
        cfg.paintImage(qp, dst)
        qp.end()

        buffer = QBuffer()
        buffer.open(QBuffer.ReadWrite)
        img.save(buffer, "JPG")
        self.wfile.write(buffer.data())


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

        self._linkedBtn = QCheckBox("verbunden", self)
        self._linkedBtn.setChecked(self.config.linked)
        self._linkedBtn.stateChanged.connect(self.config.setLinked)
        self.config.linkedChanged.connect(self.setLinked)

        self._modeGroup = QButtonGroup(self)
        self._modeGroup.addButton(QRadioButton("skalieren",self),0)
        self._modeGroup.addButton(QRadioButton("schieben",self),1)
        self._modeGroup.addButton(QRadioButton("drehen",self),2)
        self._modeGroup.addButton(QRadioButton("drehen+skalieren",self),3)
        self._modeGroup.button(self.config.mode).setChecked(True)
        self._modeGroup.buttonClicked['int'].connect(self.config.setMode)
        self.config.modeChanged.connect(self.setMode)

        tb = QHBoxLayout()
        tb.addWidget(save)
        tb.addStretch(1)
        tb.addWidget(rotleft)
        tb.addWidget(rotright)
        tb.addWidget(self._linkedBtn)
        tb.addWidget(self._modeGroup.button(0))
        tb.addWidget(self._modeGroup.button(1))
        tb.addWidget(self._modeGroup.button(2))
        tb.addWidget(self._modeGroup.button(3))
        vbox.addLayout(tb)

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

        self.httpd = ThreadingHTTPServer(('', 12345), ImageWebserver)
        self.httpd.appconfig = self.config
        self.httpd_thread = threading.Thread(target=self.httpd.serve_forever)
        self.httpd_thread.daemon = True
        self.httpd_thread.start()

    def closeEvent(self, e):
        self.httpd.shutdown()
        self.httpd.server_close()

    def setLinked(self, value):
        self._linkedBtn.setChecked(value!=0)
        self._linkedBtn.repaint()

    def setMode(self, value):
        self.config.setLinked(value==0)
        self._modeGroup.button(value).setChecked(True)

    def computeScale(self, start, end):
        try:
            p1 = start - self._mouseCenter
            p2 = end - self._mouseCenter
            s = math.sqrt(float(p2.x()*p2.x()+p2.y()*p2.y())/
                float(p1.x()*p1.x()+p1.y()*p1.y()))
            return QTransform().scale(s,s)
        except ZeroDivisionError:
            return QTransform()

    def computeMove(self, start, end):
        try:
            m = QPointF(end-start)/self.leftImage.imgRect().width()
            return QTransform(1,0,0,1,m.x(),m.y())
        except ZeroDivisionError:
            return QTransform()

    def computeRotate(self, start, end):
        try:
            p1 = start - self._mouseCenter
            p2 = end - self._mouseCenter
            return QTransform().rotateRadians(math.atan2(p1.x(),p1.y()) - math.atan2(p2.x(),p2.y()))
        except ZeroDivisionError:
            return QTransform()

    def computeRotateScale(self, start, end):
        try:
            p1 = start - self._mouseCenter
            p2 = end - self._mouseCenter
            s = float(p1.y()*p2.x()-p1.x()*p2.y())/float(p1.x()*p1.x()+p1.y()*p1.y())
            c = (p2.y()+p1.x()*s)/p1.y()
            return QTransform(c,-s,s,c,0,0)
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

        if self.config.mode == 0:
            transform = self.computeScale(self._mouseStart, self._mouseEnd)
        elif self.config.mode == 1:
            transform = self.computeMove(self._mouseStart, self._mouseEnd)
        elif self.config.mode == 2:
            transform = self.computeRotate(self._mouseStart, self._mouseEnd)
        elif self.config.mode == 3:
            transform = self.computeRotateScale(self._mouseStart, self._mouseEnd)

        if (self._mouseSide==0 or self.config.linked):
            self.config.leftState().transform = self._leftTransform * transform
        if (self._mouseSide==1 or self.config.linked):
            self.config.rightState().transform = self._rightTransform * transform


    def saveTriggered(self):
        dstFile = self.config.proposeFilename()
        if dstFile == None: return
        print("saving in "+dstFile)

        # create an image for the final output
        img = QImage(self.config.saveSize, QImage.Format_RGB888)
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


class DepthRenderThread(QThread):
    renderedImage = pyqtSignal()
    def __init__(self, w,h, l,r, parent=None):
        super(DepthRenderThread, self).__init__(parent)
        self.mutex = QMutex()
        self.condition = QWaitCondition()
        self.left = l
        self.right = r
        self.image = QImage(w, h, QImage.Format_Grayscale8)
        self.restart = False
        self.abort = False

    def __del__(self):
        self.mutex.lock()
        self.abort = True
        self.condition.wakeOne()
        self.mutex.unlock()
        self.wait()

    def updateImage(self):
        locker = QMutexLocker(self.mutex)
        if not self.isRunning():
            self.start(QThread.LowPriority)
        else:
            self.restart = True
            self.condition.wakeOne()

    def _updateImage(self):
        print("updating depth map")

        tmp = self.image.copy()
        tmp.fill(Qt.black)
        qp = QPainter(tmp)
        self.left.paintImage(qp, QRect(QPoint(0,0), tmp.size()))
        qp.end()
        ptr = tmp.constBits()
        ptr.setsize(tmp.byteCount())
        left = np.array(ptr).reshape( tmp.height(), tmp.width(), 1)

        qp = QPainter(tmp)
        self.right.paintImage(qp, QRect(QPoint(0,0), tmp.size()))
        qp.end()
        ptr = tmp.constBits()
        ptr.setsize(tmp.byteCount())
        right = np.array(ptr).reshape( tmp.height(), tmp.width(), 1)

        print("begin detection...")

        stereo = cv2.StereoBM.create(numDisparities=16, blockSize=15)

        # window_size = 3
        # min_disp = 16
        # num_disp = 112-min_disp
        # stereo = cv2.StereoSGBM.create(
        #     minDisparity = min_disp,
        #     numDisparities = num_disp,
        #     blockSize = window_size,
        #     uniquenessRatio = 10,
        #     speckleWindowSize = 100,
        #     speckleRange = 32,
        #     disp12MaxDiff = 1,
        #     P1 = 8*3*window_size**2,
        #     P2 = 32*3*window_size**2
        #     )

        #im = right
        im = stereo.compute(left, right)
        #pprint(im)
        im = (im/16).astype(np.uint8)
        print("convert result to QImage")

        # consider post processing: https://docs.opencv.org/3.1.0/d3/d14/tutorial_ximgproc_disparity_filtering.html

        self.mutex.lock()
        self.image = QImage(im.data, im.shape[1], im.shape[0], im.strides[0],
            QImage.Format_Grayscale8).copy()
        self.mutex.unlock()
        print("3d final image size "+str(self.image.width())+"x"+str(self.image.height()))


    def run(self):
        while not self.abort:
            self._updateImage()
            self.renderedImage.emit()

            self.mutex.lock()
            if not self.restart:
                self.condition.wait(self.mutex)
            self.restart = False
            self.mutex.unlock()


class DepthWindow(QWidget):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle('3D Tiefenkarte')

        self.setMinimumSize(self.config.aspectRatio.width()*5/2,
            self.config.aspectRatio.height()*5)
        self.setMaximumSize(self.config.aspectRatio.width()*50/2,
            self.config.aspectRatio.height()*50)

        aw = self.config.aspectRatio.width()
        ah = self.config.aspectRatio.height()
        self.thread = DepthRenderThread(aw*200/2, ah*200,
            self.config.leftState(), self.config.rightState(), self)
        self.thread.renderedImage.connect(self.repaint)

        self.config.leftState().changed.connect(self.thread.updateImage)
        self.config.rightState().changed.connect(self.thread.updateImage)


    def sizeHint(self):
        return QSize(self.config.aspectRatio.width()*39/2,
            self.config.aspectRatio.height()*30)

    def imgRect(self):
        aw = self.config.aspectRatio.width()
        ah = self.config.aspectRatio.height()*2
        if self.width() > aw*self.height()/ah:
            w = aw*self.height()/ah
            h = self.height()
        else:
            w = self.width()
            h = ah*self.width()/aw
        # print("3d depth size "+str(w)+"x"+str(h))
        return QRect((self.width()-w)/2,(self.height()-h)/2,w,h)

    def paintEvent(self, event):
        locker = QMutexLocker(self.thread.mutex)
        img = self.thread.image

        dst = self.imgRect()
        qp = QPainter()
        qp.begin(self)

        # draw background
        brush = QBrush(Qt.SolidPattern)
        # brush.setColor(Qt.white)
        brush.setColor(Qt.black)
        qp.setBrush(brush)
        qp.drawRect(QRect(0,0,self.width(),self.height()))

        qp.save()
        qp.translate(dst.x()+dst.width()/2, dst.y()+dst.height()/2)
        qp.scale(dst.width()/img.width(), dst.width()/img.width())
        qp.translate(-img.width()/2, -img.height()/2)
        qp.drawImage(0,0,img)
        qp.restore()

        # draw orientation lines
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


if __name__ == '__main__':

    app = QApplication(sys.argv)
    config = GlobalConfig()
    iw = ImageWindow(config)
    iw.show()
    dp = DepthWindow(config)
    dp.show()

    sys.exit(app.exec_())
