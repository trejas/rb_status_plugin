from datetime import timedelta
from airflow import DAG, configuration
from airflow.operators.python_operator import PythonOperator
from airflow.operators.latest_only_operator import LatestOnlyOperator
import airflow.utils.dates as dt

from rb_status_plugin.core.report_repo import VariablesReportRepo
from rb_status_plugin.sensors.status_sensor import StatusSensor
from rb_status_plugin.core.helpers.email_helpers import report_notify_email


# Default settings applied to all tests
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 0,
    "start_date": dt.days_ago(1),
    "retry_delay": timedelta(minutes=5),
    "catchup": False,
}

plugin_path = configuration.get("core", "plugins_folder")
# Consider moving these constants to an Airflow variable...
EMAIL_TEMPLATE_LOCATION = f"{plugin_path}/rb_status_plugin/templates/emails"
SINGLE_EMAIL_TEMPLATE = f"{EMAIL_TEMPLATE_LOCATION}/single_report.html"


def create_dag(report, default_args):
    dag = DAG(
        report.dag_id, schedule_interval=report.schedule, default_args=default_args
    )

    with dag:
        test_prefix = "test_"

        start = LatestOnlyOperator(task_id="start_dag")
        send_email = PythonOperator(
            task_id="call_email_function",
            python_callable=report_notify_email,
            trigger_rule="all_done",
            op_kwargs={
                "report": report,
                "email_template_location": SINGLE_EMAIL_TEMPLATE,
            },
            provide_context=True,
        )
        for test in report.tests:
            t1 = StatusSensor(
                task_id=test_prefix + test,
                test_dag_id=test.split(".")[0],
                test_task_id=test.split(".")[1],
            )
            start >> t1 >> send_email

    return dag


report = []
for report in VariablesReportRepo.list():
    globals()[report.name] = create_dag(report, default_args)
