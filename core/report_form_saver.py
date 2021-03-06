from airflow.models import Variable
import json
import logging
import re
from flask import flash
from inflection import parameterize
import pendulum
from rb_status_plugin.core.report_repo import VariablesReportRepo


class ReportFormSaver:
    """
    A class for properly saving a report's form into an airflow variable.
    """

    report_dict = {}

    def __init__(self, form):
        """
        :param self.report_dict: a mapping of form attributes to inputted values
        :type self.report_dict: Dict

        :param form: report being parsed and saved
        :type form: ReportForm
        """
        self.form = form
        self.format_emails()
        self.report_dict["report_title"] = self.form.report_title.data
        self.report_dict["report_title_id"] = parameterize(self.form.report_title.data)
        self.report_dict["description"] = self.form.description.data
        self.report_dict["owner_name"] = self.form.owner_name.data
        self.report_dict["owner_email"] = self.form.owner_email.data
        self.report_dict["tests"] = self.form.tests.data
        self.report_dict["schedule_type"] = self.form.schedule_type.data
        self.report_dict["schedule_timezone"] = self.form.schedule_timezone.data
        if self.report_dict["schedule_type"] == "custom":
            self.report_dict["schedule"] = self.form.schedule_custom.data
        elif self.report_dict["schedule_type"] == "manual":
            self.report_dict["schedule"] = None
        else:
            utc_week_day, utc_time = self.get_utc_time_and_week_day()
            self.report_dict["schedule_time"] = utc_time
            if self.report_dict["schedule_type"] == "weekly":
                self.report_dict["schedule_week_day"] = utc_week_day
            self.report_dict["schedule"] = self.get_cron_schedule()

    def extract_report_data_into_airflow(self, report_exists):
        """
        Extract output of report form into a formatted airflow variable.

        :param report_exists: whether the report exists
        :type report_exists: Boolean

        Return boolean on whether form submitted.
        """

        # if report looks good, save it
        if self.validate_unique_report(report_exists):
            report_json = json.dumps(self.report_dict)
            Variable.set(key=self.report_dict["report_id"], value=report_json)
            return True
        return False

    def validate_unique_report(self, report_exists):
        """
        Check that report has unique name/key.

        :param report_exists: whether the report exists
        :type report_exists: Boolean

        Return boolean on whether report is unique.
        """

        if self.check_empty_fields() and self.emails_formatted:
            if report_exists:
                self.report_dict["report_id"] = self.form.report_id.data
            else:
                self.report_dict["report_id"] = (
                    f"{VariablesReportRepo.report_prefix}"
                    f"""{self.report_dict["report_title"]}"""
                )
                if not self.check_unique_field(report_exists, "report_id"):
                    return False
            if self.check_unique_field(report_exists, "report_title_id"):
                return True
        return False

    def check_unique_field(self, report_exists, field_name):
        """
        Check if field is already exists.

        :param report_exists: whether the report exists
        :type report_exists: Boolean

        :param field_name: name of report attribute
        :type field_name: String

        Return boolean on whether entry is unique.
        """

        for report in VariablesReportRepo.list():
            # dont check against the report being editted
            if report_exists:
                if getattr(report, "report_id") == self.report_dict["report_id"]:
                    continue

            # alert user that field_name is being used by another report
            if str(getattr(report, field_name)) == self.report_dict[field_name]:
                logging.error(
                    "Error: %s (%s) already taken."
                    % (field_name, self.report_dict[field_name])
                )
                flash(
                    "Error: %s (%s) already taken."
                    % (field_name, self.report_dict[field_name])
                )
                return False
        return True

    def check_empty_field(self, field_name):
        """
        Check for empty data in field.

        :param field_name: name of report attribute
        :type field_name: String

        Return boolean on whether field is filled.
        """

        if self.report_dict[field_name] or self.report_dict[field_name] == 0:
            return True

        # manual schedules will store a null schedule field
        if self.report_dict["schedule_type"] == "manual":
            if field_name == "schedule":
                return True

        logging.info(f"Error: {field_name} can not be empty.")
        flash(f"Error: {field_name} can not be empty.")
        return False

    def check_empty_fields(self):
        """
        Check for input in each field (except subscribers).

        Return boolean on whether fields are filled out.
        """

        form_completed = True
        for field_name in self.report_dict.keys():
            if field_name != "subscribers":
                form_completed = form_completed and self.check_empty_field(field_name)
        return form_completed

    def format_emails(self):
        """
        Parse, transform, and vaildate emails.
        """

        self.emails_formatted = True

        # owner_email should be a single email
        emails = self.form.owner_email.data.split(",")
        if len(emails) != 1:
            logging.info("Error: Exactly one email is required for Owner Email field.")
            flash("Error: Exactly one email is required for Owner Email field.")
            self.emails_formatted = False

        # Add owner's email to subscribers; dedupe, order, & format subscribers
        emails += self.form.subscribers.data.split(",")
        emails = list(set([email.replace(" ", "") for email in emails]))
        emails = [email for email in emails if email]
        emails.sort()
        if False in [self.validate_email(email) for email in emails]:
            self.emails_formatted = False

        # add updated list to subscribers, only if valid
        if self.emails_formatted:
            self.report_dict["subscribers"] = emails

    def validate_email(self, email):
        """
        Check that an email is properly formatted.

        :param email: an email address
        :type email: String

        Return boolean on whether email is valid.
        """

        email_format = re.compile(r"^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$")

        if not re.search(email_format, email):
            logging.info(
                f"Email ({email}) is not valid. Please enter a valid email address."
            )
            flash(f"Email ({email}) is not valid. Please enter a valid email address.")
            return False

    def get_utc_time_and_week_day(self):
        """
        Get schedule time and weekday in UTC timezone
        """
        time = self.form.schedule_time.data
        week_day = self.form.schedule_week_day.data
        tz = self.report_dict["schedule_timezone"]

        dt = pendulum.now()
        dt = dt.in_tz(tz)
        if week_day:
            dt = dt.next(int(week_day))
        dt = dt.at(time.hour, time.minute, 0)
        dt = dt.in_tz("UTC")

        return (dt.day_of_week, dt.strftime("%H:%M"))

    def get_cron_schedule(self):
        """
        Convert schedule time and weekday into cron schedule
        """
        hour, minute = [
            int(value) for value in self.report_dict["schedule_time"].split(":")
        ]
        cron_expression = f"{minute} {hour} * * "
        if self.report_dict["schedule_type"] == "weekly":
            cron_expression += str(self.report_dict["schedule_week_day"])
        else:
            cron_expression += "*"

        return cron_expression

    @classmethod
    def load_form(cls, form, requested_report):
        """
        Update form using a requested report's configuation.

        :param form: form to populate UI
        :type form: ReportForm

        :param requested_report: contains a Report configuration.
        :type requested_report: Report

        return form
        """
        form.report_id.data = requested_report.report_id
        form.report_title.data = requested_report.report_title
        form.description.data = requested_report.description
        form.owner_name.data = requested_report.owner_name
        form.owner_email.data = requested_report.owner_email
        form.subscribers.data = ", ".join(requested_report.subscribers)
        form.schedule_type.data = requested_report.schedule_type
        if form.schedule_type.data == "custom":
            form.schedule_custom.data = requested_report.schedule
        if form.schedule_type.data == "daily":
            form.schedule_time.data = requested_report.schedule_time
        if form.schedule_type.data == "weekly":
            form.schedule_time.data = requested_report.schedule_time
            form.schedule_week_day.data = str(requested_report.schedule_week_day)
        form.tests.data = requested_report.tests
        return form
