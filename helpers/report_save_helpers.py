from airflow.models import Variable
import json
import logging
import re
from flask import flash
from inflection import parameterize

from lumen_plugin.report_repo import VariablesReportRepo


class SaveReportForm:
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
        self.report_dict["report_title"] = self.form.title.data
        self.report_dict["report_title_url"] = parameterize(self.form.title.data)
        self.report_dict["description"] = self.form.description.data
        self.report_dict["owner_name"] = self.form.owner_name.data
        self.report_dict["owner_email"] = self.form.owner_email.data
        self.report_dict["subscribers"] = self.form.subscribers.data
        self.report_dict["tests"] = self.form.tests.data
        self.report_dict["schedule_type"] = self.form.schedule_type.data
        if self.report_dict["schedule_type"] == "custom":
            self.report_dict["schedule"] = self.form.schedule_custom.data
        elif self.report_dict["schedule_type"] == "manual":
            self.report_dict["schedule"] = None
        else:
            self.report_dict["schedule_time"] = None
            self.convert_schedule_to_cron_expression()

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

        if self.check_empty_fields():
            if report_exists:
                self.report_dict["report_id"] = self.form.report_id.data
            else:
                self.report_dict["report_id"] = "%s%s" % (
                    VariablesReportRepo.report_prefix,
                    self.report_dict["report_title"],
                )
                if not self.check_unique_field(report_exists, "report_id"):
                    return False
            if self.check_unique_field(report_exists, "report_title_url"):
                return True
        return False

    def check_unique_field(self, report_exists, field_name):
        """
        Chack if field is already exists.

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
                logging.exception(
                    "Error: %s (%s) already taken."
                    % (field_name, self.report_dict[field_name])
                )
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

        if self.report_dict[field_name]:
            return True

        # manual schedules will store a null schedule field
        if self.report_dict["schedule_type"] == "manual":
            if field_name == "schedule":
                return True

        logging.exception("Error: %s can not be empty." % (field_name))
        logging.error("Error: %s can not be empty." % (field_name))
        flash("Error: %s can not be empty." % (field_name))
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

        # owner_email should be a single email
        emails = self.form.owner_email.data.split(",")
        if len(emails) != 1:
            logging.exception(
                "Error: Exactly one email is required for Owner Email field."
            )
            logging.error("Error: Exactly one email is required for Owner Email field.")
            flash("Error: Exactly one email is required for Owner Email field.")

        # Add owner's email to subscribers; dedupe, order, & format subscribers
        emails += self.form.subscribers.data.split(",")
        emails = list(set([email.replace(" ", "") for email in emails]))
        emails = [email for email in emails if email]
        emails.sort()
        [self.validate_email(email) for email in emails]
        self.form.subscribers.data = emails

    def validate_email(self, email):
        """
        Check that an email is properly formatted.

        :param email: an email address
        :type email: String
        """

        email_format = re.compile(r"^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$")

        if not re.search(email_format, email):
            logging.exception(
                "Email (%s) is not valid. Please enter a valid email address." % email
            )
            logging.error(
                "Email (%s) is not valid. Please enter a valid email address." % email
            )
            flash(
                "Email (%s) is not valid. Please enter a valid email address." % email
            )

    def convert_schedule_to_cron_expression(self):
        """
        Convert Weekly and Daily schedules into a cron expression, and
        saves attributes to self.report_dict
        """

        try:
            # add time of day
            time_of_day = self.form.schedule_time.data.strftime("%H:%M")
            self.report_dict["schedule_time"] = time_of_day
            hour, minute = time_of_day.split(":")
            cron_expression = "%s %s * * " % (minute, hour)

            # add day of week if applicable
            if self.form.schedule_type.data == "weekly":
                cron_expression += self.form.schedule_week_day.data
                self.report_dict["schedule_week_day"] = self.form.schedule_week_day.data
            else:
                cron_expression += "*"

            self.report_dict["schedule"] = cron_expression
        except AttributeError:
            logging.exception("Error: Schedule's time is invalid.")
            logging.error("Error: Schedule's time is invalid.")
            flash("Error: Schedule's time is invalid.")
