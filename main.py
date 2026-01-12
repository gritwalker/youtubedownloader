import os
import sys
import shutil
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QThread
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QProgressBar,
    QPlainTextEdit,
    QGroupBox,
    QFormLayout,
    QMessageBox,
)
import yt_dlp


class DownloadWorker(QObject):
    progress = pyqtSignal(int, str)
    log = pyqtSignal(str)
    finished = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, url: str, output_dir: str, ffmpeg_available: bool):
        super().__init__()
        self.url = url
        self.output_dir = output_dir
        self.ffmpeg_available = ffmpeg_available
        self._logger = self._build_logger()

    def _build_logger(self):
        # yt-dlp logger bridge to forward messages into UI
        class _Logger:
            def __init__(self, emit):
                self.emit = emit

            def debug(self, msg):
                if isinstance(msg, bytes):
                    msg = msg.decode(errors="ignore")
                self.emit(str(msg))

            def warning(self, msg):
                if isinstance(msg, bytes):
                    msg = msg.decode(errors="ignore")
                self.emit(f"경고: {msg}")

            def error(self, msg):
                if isinstance(msg, bytes):
                    msg = msg.decode(errors="ignore")
                self.emit(f"오류: {msg}")

        return _Logger(self.log.emit)

    def _progress_hook(self, d):
        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            percent = int(downloaded * 100 / total) if total else 0
            speed = d.get("speed")
            eta = d.get("eta")
            info = d.get("info_dict") or {}
            p_index = info.get("playlist_index")
            p_count = info.get("playlist_count")
            prefix = ""
            if isinstance(p_index, int) and isinstance(p_count, int) and p_count > 0:
                prefix = f"[{p_index}/{p_count}] "
            desc = prefix
            if speed:
                desc += f"{int(speed/1024)} KB/s "
            if eta is not None:
                desc += f"ETA {eta}s"
            self.progress.emit(percent, desc.strip())
        elif d.get("status") == "finished":
            info = d.get("info_dict") or {}
            p_index = info.get("playlist_index")
            p_count = info.get("playlist_count")
            prefix = ""
            if isinstance(p_index, int) and isinstance(p_count, int) and p_count > 0:
                prefix = f"[{p_index}/{p_count}] "
            self.progress.emit(100, f"{prefix}병합 중".strip())

    def run(self):
        try:
            outtmpl = os.path.join(self.output_dir, "%(title)s.%(ext)s")
            if self.ffmpeg_available:
                ydl_opts = {
                    "outtmpl": outtmpl,
                    "ignoreerrors": True,
                    "merge_output_format": "mp4",
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "progress_hooks": [self._progress_hook],
                    "logger": self._logger,
                }
            else:
                ydl_opts = {
                    "outtmpl": outtmpl,
                    "ignoreerrors": True,
                    "format": "best[ext=mp4]/best",
                    "progress_hooks": [self._progress_hook],
                    "logger": self._logger,
                }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                self.log.emit("정보 수집 중")
                ydl.download([self.url])
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("YouTube 다운로더")
        self.setMinimumSize(720, 520)
        self._apply_light_theme()
        self.thread = None
        self.worker = None
        self.ffmpeg_available = shutil.which("ffmpeg") is not None
        self._build_ui()

    def _apply_light_theme(self):
        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#222222"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#FAFAFA"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F0F0F0"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#222222"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#222222"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#F7F7F7"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#222222"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#1976D2"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        self.setPalette(palette)
        self.setStyleSheet(
            """
            QLineEdit, QPlainTextEdit {
                border: 1px solid #D0D0D0;
                border-radius: 6px;
                padding: 6px;
                background: #FFFFFF;
            }
            QPushButton {
                border: 1px solid #C8D6E5;
                border-radius: 6px;
                padding: 8px 12px;
                background: #E3F2FD;
                color: #0D47A1;
            }
            QPushButton:disabled {
                background: #EEEEEE;
                color: #888888;
            }
            QGroupBox {
                border: 1px solid #E0E0E0;
                border-radius: 8px;
                margin-top: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 6px;
            }
            QProgressBar {
                border: 1px solid #D0D0D0;
                border-radius: 6px;
                text-align: center;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #64B5F6;
                border-radius: 6px;
            }
            """
        )

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout()

        form_group = QGroupBox("입력")
        form = QFormLayout()

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("유튜브 영상 또는 재생목록 URL")
        form.addRow(QLabel("URL"), self.url_edit)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("다운로드 폴더")
        browse_btn = QPushButton("폴더 선택")
        browse_btn.clicked.connect(self.on_browse)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)
        path_wrap = QWidget()
        path_wrap.setLayout(path_row)
        form.addRow(QLabel("저장 위치"), path_wrap)

        actions_row = QHBoxLayout()
        self.start_btn = QPushButton("다운로드 시작")
        self.start_btn.clicked.connect(self.on_start)
        actions_row.addWidget(self.start_btn)
        actions_wrap = QWidget()
        actions_wrap.setLayout(actions_row)
        form.addRow(QLabel("작업"), actions_wrap)

        form_group.setLayout(form)
        root.addWidget(form_group)

        status_group = QGroupBox("상태")
        status_layout = QVBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.status_label = QLabel("대기 중")
        status_layout.addWidget(self.progress)
        status_layout.addWidget(self.status_label)
        self.ffmpeg_label = QLabel()
        self.ffmpeg_label.setTextFormat(Qt.TextFormat.RichText)
        self.ffmpeg_label.setOpenExternalLinks(True)
        self.ffmpeg_label.setStyleSheet("color: #666666; font-size: 12px;")
        if self.ffmpeg_available:
            self.ffmpeg_label.setText("ffmpeg 감지됨: mp4 병합 사용")
        else:
            self.ffmpeg_label.setText(
                'ffmpeg 미감지: 단일 스트림으로 저장됨 (설치 안내: <a href="https://www.gyan.dev/ffmpeg/builds/">Windows FFmpeg 다운로드</a>)'
            )
        status_layout.addWidget(self.ffmpeg_label)
        status_group.setLayout(status_layout)
        root.addWidget(status_group)

        log_group = QGroupBox("로그")
        log_layout = QVBoxLayout()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        root.addWidget(log_group)

        central.setLayout(root)
        self.setCentralWidget(central)

    def on_browse(self):
        path = QFileDialog.getExistingDirectory(self, "다운로드 폴더 선택")
        if path:
            self.path_edit.setText(path)

    def on_start(self):
        url = self.url_edit.text().strip()
        output_dir = self.path_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "입력 오류", "URL을 입력하세요.")
            return
        if not output_dir:
            QMessageBox.warning(self, "입력 오류", "다운로드 폴더를 선택하세요.")
            return
        if not os.path.isdir(output_dir):
            QMessageBox.warning(self, "입력 오류", "유효한 폴더가 아닙니다.")
            return
        self.start_btn.setEnabled(False)
        self.progress.setValue(0)
        self.status_label.setText("시작 중")
        self.log_view.clear()
        self.thread = QThread()
        self.worker = DownloadWorker(url, output_dir, self.ffmpeg_available)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.on_progress)
        self.worker.log.connect(self.append_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.thread.start()

    def on_progress(self, value: int, desc: str):
        self.progress.setValue(value)
        self.status_label.setText(f"진행률 {value}%{(' - ' + desc) if desc else ''}")

    def append_log(self, text: str):
        self.log_view.appendPlainText(text)

    def on_finished(self):
        self.append_log("완료")
        self.status_label.setText("완료")
        self.start_btn.setEnabled(True)
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.worker = None

    def on_error(self, message: str):
        self.append_log(f"오류: {message}")
        self.status_label.setText("오류")
        self.start_btn.setEnabled(True)
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None
            self.worker = None


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
