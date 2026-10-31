from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,main
from unittest.mock import patch
import json,wave
from lecture_agent import retention

class RetentionTests(TestCase):
    def fixture(self,root):
        (root/'lesson.yaml').write_text('inputs: {}')
        for name,text in {'08_report/课程讲解报告.md':'[视频](../00_sources/video/lecture.mp4)',
                          '08_report/课程讲解报告.html':'<a href="../00_sources/video/lecture.mp4">视频</a>',
                          '07_record/ready/record.md':'record','00_sources/sources.jsonl':'',
                          '00_sources/video/lecture.mp4':'test-video','00_sources/documents/book.pdf':'book',
                          '02_frames/board/frame.jpg':'image'}.items():
            path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
        (root/'01_audio').mkdir()
        with wave.open(str(root/'01_audio/audio.wav'),'wb') as wav:
            wav.setparams((1,2,16000,0,'NONE','not compressed'));wav.writeframes(b'\0\0'*16000)
        (root/'09_quality').mkdir()
        for name in ['record_gate.json','report_gate.json']:
            (root/'09_quality'/name).write_text(json.dumps({'status':'completed','full_lesson_covered':True,'source_checks_completed':True}))
        (root/'status.json').write_text('{}')

    def test_cleanup_after_verified_report_preserves_nonmedia(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);self.fixture(root)
            with patch('lecture_agent.cli.verify',return_value=0),patch.object(retention.subprocess,'run'):
                result=retention.confirm_and_cleanup(root)
            self.assertEqual(result['status'],'completed')
            self.assertFalse((root/'00_sources/video/lecture.mp4').exists())
            self.assertFalse((root/'01_audio/audio.wav').exists())
            self.assertTrue((root/'00_sources/documents/book.pdf').exists())
            self.assertTrue((root/'02_frames/board/frame.jpg').exists())
            self.assertTrue(retention.removed(root,'01_audio/audio.wav'))
            self.assertEqual(retention.audio_duration(root),1)
            self.assertNotIn('](../00_sources/video/lecture.mp4)',(root/'08_report/课程讲解报告.md').read_text())

    def test_failed_verification_keeps_media(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);self.fixture(root)
            with patch('lecture_agent.cli.verify',return_value=1):
                with self.assertRaises(RuntimeError):retention.confirm_and_cleanup(root)
            self.assertTrue((root/'00_sources/video/lecture.mp4').exists())

    def test_incomplete_gate_keeps_media(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);self.fixture(root)
            (root/'09_quality/report_gate.json').write_text('{"status":"incomplete"}')
            with self.assertRaises(RuntimeError):retention.confirm_and_cleanup(root)
            self.assertTrue((root/'01_audio/audio.wav').exists())

if __name__=='__main__':main()
