from pathlib import Path
from tempfile import TemporaryDirectory
import json,sys
from unittest import TestCase,main
from lecture_agent.background import supervise

class BackgroundTests(TestCase):
    def job(self,root,command):
        lesson=root/'lesson';lesson.mkdir();job=lesson/'_runs/background/test';job.mkdir(parents=True)
        (job/'request.json').write_text(json.dumps({'job_id':'test','lesson':str(lesson),'stage':'test','command':command,
                                                  'report_interval_seconds':.05,'process_check_seconds':.01}))
        return job

    def test_periodic_then_success(self):
        with TemporaryDirectory() as temporary:
            job=self.job(Path(temporary),[sys.executable,'-c','import time; time.sleep(.18); print("done")'])
            self.assertEqual(supervise(job),0)
            reports=[json.loads(line) for line in (job/'reports.jsonl').read_text().splitlines()]
            self.assertEqual(reports[0]['reason'],'started')
            self.assertTrue(any(row['reason']=='periodic' for row in reports))
            self.assertEqual(reports[-1]['status'],'completed')
            self.assertEqual(reports[-1]['exit_code'],0)
            self.assertIn('done',(job/'worker.log').read_text())

    def test_failure_is_reported(self):
        with TemporaryDirectory() as temporary:
            job=self.job(Path(temporary),[sys.executable,'-c','raise SystemExit(7)'])
            self.assertEqual(supervise(job),7)
            state=json.loads((job/'status.json').read_text())
            self.assertEqual(state['status'],'failed')
            self.assertEqual(state['exit_code'],7)

    def test_success_continues_immediately_and_failure_does_not(self):
        for first_exit in (0,7):
            with self.subTest(first_exit=first_exit), TemporaryDirectory() as temporary:
                root=Path(temporary); marker=root/'continued'
                job=self.job(root,[sys.executable,'-c',f'raise SystemExit({first_exit})'])
                request=json.loads((job/'request.json').read_text())
                request['continuation_command']=[sys.executable,'-c',f'from pathlib import Path; Path({str(marker)!r}).write_text("ok")']
                (job/'request.json').write_text(json.dumps(request))
                self.assertEqual(supervise(job),first_exit)
                self.assertEqual(marker.exists(),first_exit==0)
                reports=[json.loads(line) for line in (job/'reports.jsonl').read_text().splitlines()]
                self.assertEqual(any(row['reason']=='continued' for row in reports),first_exit==0)

    def test_pipeline_reports_periodically_only_during_asr(self):
        for stage in ('asr','finish'):
            with self.subTest(stage=stage), TemporaryDirectory() as temporary:
                job=self.job(Path(temporary),[sys.executable,'-c','import time; time.sleep(.16)'])
                request=json.loads((job/'request.json').read_text());request['stage']='pipeline'
                (job/'request.json').write_text(json.dumps(request))
                pipeline=job.parent.parent/'pipeline';pipeline.mkdir()
                (pipeline/'status.json').write_text(json.dumps({'stage':stage}))
                self.assertEqual(supervise(job),0)
                reports=[json.loads(line) for line in (job/'reports.jsonl').read_text().splitlines()]
                self.assertEqual(any(row['reason']=='periodic' for row in reports),stage=='asr')

if __name__=='__main__':main()
