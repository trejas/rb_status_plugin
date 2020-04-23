from airflow.operators.email_operator import EmailOperator
from airflow.models.taskinstance import TaskInstance
from plugins.lumen_plugin.report_instance import ReportInstance
from airflow.utils.state import State
from datetime import datetime
import re
import logging


def create_report_instance(context):
    return ReportInstance(context["dag_run"])


def get_test_status(report_instance):
    """
    Uses the report_instance passed via the Python Operator
    and create a list with all test status values
    """
    return report_instance.errors()


def get_error_details(test_prefix, errors):
    """
    This just returns the first error log link
    """
    for failed_task in errors:
        if re.match(test_prefix, failed_task["name"]) is not None:
            return failed_task["description"]


def are_all_tasks_successful(test_prefix, errors):
    """
    Iterate over all the test tasks status and return True if all pass
    and False if otherwise
    """

    if len(errors) == 0:
        return True

    for failed_task in errors:
        # If the failed task is a test task
        if re.match(test_prefix, failed_task["name"]) is not None:
            return False

    return True


def report_notify_email(emails, email_template_location, test_prefix, **context):
    """
    :param emails: emails to send report status to
    :type emails: list

    :param email_template_location: location of html template to use for status
    :type email_template_location: str

    :param test_prefix: the prefix that precedes all test tasks
    :type test_prefix: str
    """
    ri = create_report_instance(context)

    dag_name = ri.id
    updated_time = ri.updated
    errors = get_test_status(ri)
    details_link = get_error_details(test_prefix, errors)
    passed = are_all_tasks_successful(test_prefix, errors)

    if passed:
        status = "Success"
    else:
        status = "Failed"

    with open(email_template_location) as file:
        send_email = EmailOperator(
            task_id="custom_email_notification",
            to=emails,
            subject="[{{status}}] {{title}}",
            html_content=file.read(),
        )
        params = {
            "passed": passed,
            "status": status,
            "updated": updated_time,
            "title": dag_name,
            "details_link": "#",
        }
        send_email.render_template_fields(
            context=params, jinja_env=context["dag"].get_template_env()
        )
        logging.info(f'Sending "{send_email.subject}" email...')
        send_email.execute(context)
