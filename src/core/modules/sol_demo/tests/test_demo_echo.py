from odoo.tests import TransactionCase, tagged

from odoo.addons.sol_laboratory.constants.models import MODEL_SCHEDULED_JOB


@tagged("post_install", "-at_install")
class TestDemoEcho(TransactionCase):
    def test_the_demo_job_logs_a_message_and_can_fail(self):
        job = self.env[MODEL_SCHEDULED_JOB]
        done = job.queue("demo.echo", "demo-ok", payload={"message": "hello"})
        job._handle_demo_echo(done)

        failing = job.queue("demo.echo", "demo-fail", payload={"fail": True, "message": "stop"})
        with self.assertRaises(ValueError):
            job._handle_demo_echo(failing)
