from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase,main
from unittest.mock import patch
import json,yaml,wave
from lecture_agent import pipeline

class PipelineTests(TestCase):
    def project(self,root):
        (root/'configs').mkdir()
        config={'asr':{'model':'whisper-large-v3-turbo-4bit','chunk_seconds':300},'frames':{'sample_seconds':10},
                'agent':{'model':'gpt-6.1-terra','reasoning_effort':'medium'}}
        (root/'configs/default.yaml').write_text(yaml.safe_dump(config))

    def test_init_and_refuse_overwrite(self):
        with TemporaryDirectory() as temporary,patch.object(pipeline,'PROJECT',Path(temporary)):
            root=Path(temporary);self.project(root)
            lesson=pipeline.initialize('测试课程',1,1,'示例','2026-10-31',[0,0,1280,720])
            self.assertEqual(lesson.name,'第01周（1）-示例')
            self.assertFalse(any(pipeline.ready(lesson,stage) for stage in pipeline.STAGES))
            with self.assertRaises(ValueError):pipeline.initialize('测试课程',1,1,'示例','2026-10-31',[0,0,1280,720])
            with self.assertRaises(ValueError):pipeline.initialize('../escape',1,1,'示例','2026-10-31',[0,0,1280,720])

    def test_cached_run_does_not_start_any_worker_or_model(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'lesson.yaml').write_text('inputs: {video: video.mp4, slides: null, textbook: null}')
            pipeline.save(root/'_runs/pipeline/frozen.json',{'fingerprint':'same'})
            with patch.object(pipeline,'fingerprint',return_value='same'),patch.object(pipeline,'ready',return_value=True),patch.object(pipeline,'verify') as verify,patch.object(pipeline.subprocess,'run') as launch:
                pipeline.run(root)
                verify.assert_called_once_with(root);launch.assert_not_called()

    def test_changed_complete_outputs_are_not_overwritten(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'lesson.yaml').write_text('inputs: {video: video.mp4, slides: null, textbook: null}')
            pipeline.save(root/'_runs/pipeline/frozen.json',{'fingerprint':'old'})
            with patch.object(pipeline,'fingerprint',return_value='changed'),patch.object(pipeline,'ready',return_value=True),patch.object(pipeline.subprocess,'run') as launch:
                with self.assertRaises(RuntimeError):pipeline.run(root)
                launch.assert_not_called()

    def test_existing_files_do_not_override_incomplete_gate(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'lesson.yaml').write_text('inputs: {}')
            files=('07_record/ready/record.md','07_record/ready/record.html','07_record/ready/record.json',
                   '03_board/reviewed/板书文本校订稿.md','03_board/reviewed/板书文本校订稿.html','08_report/课程讲解报告.md','08_report/课程讲解报告.html')
            for name in files:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('exists')
            pipeline.save(root/'09_quality/board_review.json',{'status':'completed','all_supplied_transcript_reviewed':True})
            pipeline.save(root/'09_quality/record_gate.json',{'status':'completed','full_lesson_covered':False})
            pipeline.save(root/'09_quality/report_gate.json',{'status':'completed','full_lesson_covered':True,'source_checks_completed':True})
            self.assertFalse(pipeline.ready(root,'finish'))

    def test_asr_checkpoint_from_another_model_is_not_reused(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'lesson.yaml').write_text('asr: {model: expected-model, chunk_seconds: 300}')
            (root/'01_audio').mkdir()
            with wave.open(str(root/'01_audio/audio.wav'),'wb') as audio:
                audio.setparams((1,2,16000,0,'NONE','not compressed'));audio.writeframes(b'\x00\x00'*16000)
            pipeline.save(root/'04_transcripts/lecture_segments.json',{'duration':1,'segments':[]})
            pipeline.save(root/'04_transcripts/asr_complete.json',{'complete':True,'chunks':1,'segments':0})
            pipeline.save(root/'04_transcripts/chunk_000.json',{'chunk_start':0,'model_source':'/models/wrong-model'})
            self.assertFalse(pipeline.ready(root,'asr'))

if __name__=='__main__':main()
