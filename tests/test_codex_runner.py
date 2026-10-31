"""A zero exit code plus files must not accept an explicitly unfinished review."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch
import json
import yaml
from lecture_agent import codex_runner

class CompletionGateTests(TestCase):
    def test_unfinished_existing_output_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'configs').mkdir()
            (root/'configs/default.yaml').write_text(yaml.safe_dump({'agent':{'model':'gpt-6.1-terra','reasoning_effort':'medium'}}))
            lesson=root/'lesson';lesson.mkdir();(lesson/'review.json').write_text('{"status":"incomplete"}')
            with patch.object(codex_runner,'PROJECT',root),patch.object(Path,'home',return_value=root),patch.object(codex_runner.shutil,'which',return_value='/codex'),patch.object(codex_runner.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
                with self.assertRaises(RuntimeError):
                    codex_runner.execute(lesson,'review','Review',expected_outputs=['review.json'],gates={'review.json':{'status':'completed'}})
                command=run.call_args.args[0]
                self.assertEqual(command[command.index('--model')+1],'gpt-6.1-terra')
                self.assertIn('model_reasoning_effort="medium"',command)
                folder=lesson/'_runs/workflow_validation/codex/review'
                self.assertFalse((folder/'completed.json').exists())
                self.assertEqual(json.loads((folder/'execution.json').read_text())['status'],'incomplete')

    def test_changed_gate_invalidates_completed_checkpoint(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'configs').mkdir()
            (root/'configs/default.yaml').write_text(yaml.safe_dump({'agent':{'model':'gpt-6.1-terra','reasoning_effort':'medium'}}))
            lesson=root/'lesson';lesson.mkdir();output=lesson/'review.json';output.write_text('{"status":"completed"}')
            with patch.object(codex_runner,'PROJECT',root),patch.object(Path,'home',return_value=root),patch.object(codex_runner.shutil,'which',return_value='/codex'),patch.object(codex_runner.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run:
                args=dict(expected_outputs=['review.json'],gates={'review.json':{'status':'completed'}})
                codex_runner.execute(lesson,'review','Review',**args)
                codex_runner.execute(lesson,'review','Review',**args)
                self.assertEqual(run.call_count,1)
                output.write_text('{"status":"incomplete"}')
                with self.assertRaises(RuntimeError):codex_runner.execute(lesson,'review','Review',**args)
                self.assertEqual(run.call_count,2)

if __name__=='__main__':main()
