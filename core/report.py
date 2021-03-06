import inflection
import datetime

from airflow.utils.db import provide_session
from airflow.configuration import conf
from airflow.exceptions import DagNotFound, DagRunAlreadyExists
from airflow import models
from airflow.models import DagBag, DagModel, DagRun, Variable
from airflow.utils import timezone
from airflow.utils.state import State
from sqlalchemy import or_
from airflow.models.serialized_dag import SerializedDagModel


STORE_SERIALIZED_DAGS = conf.getboolean("core", "store_serialized_dags", fallback=False)


class Report:
    """
    Report holds a status report configuration.  It is used to build
    status report DAGs
    """

    def __init__(self, name):
        self.name = name
        self.__report_id = None
        self.__report_title = None
        self.__report_title_id = None
        self.__description = None
        self.__owner_name = None
        self.__owner_email = None
        self.__subscribers = None
        self.__tests = None
        self.__schedule_type = None
        self.__schedule_time = None
        self.__schedule_week_day = None
        self.__schedule = None

    @property
    def report_title(self):
        """ Title of the report """
        return self.__report_title

    @report_title.setter
    def report_title(self, val):
        self.__report_title = val

    @property
    def report_id(self):
        """ Unique Id of the report """
        return self.__report_id

    @report_id.setter
    def report_id(self, val):
        self.__report_id = val

    @property
    def report_title_id(self):
        """ Formatted title of the report for url path """
        return self.__report_title_id

    @report_title_id.setter
    def report_title_id(self, val):
        self.__report_title_id = val

    @property
    def description(self):
        """ Description of the report """
        return self.__description

    @description.setter
    def description(self, val):
        self.__description = val

    @property
    def owner_name(self):
        """ Name of the report owner """
        return self.__owner_name

    @owner_name.setter
    def owner_name(self, val):
        self.__owner_name = val

    @property
    def owner_email(self):
        """ Email address of the report owner """
        return self.__owner_email

    @owner_email.setter
    def owner_email(self, val):
        self.__owner_email = val

    @property
    def subscribers(self):
        """ Emails that the report will go to """
        return self.__subscribers

    @subscribers.setter
    def subscribers(self, val):
        self.__subscribers = val

    @property
    def schedule_type(self):
        """ Type of schedule (daily, weekly, custom) """
        return self.__schedule_type

    @schedule_type.setter
    def schedule_type(self, val):
        self.__schedule_type = val

    @property
    def schedule_time(self):
        """ Hour:Min of schedule (for daily & weekly) """
        return self.__schedule_time

    @schedule_time.setter
    def schedule_time(self, val):
        self.__schedule_time = datetime.datetime.strptime(val, "%H:%M")

    @property
    def schedule_week_day(self):
        """ Day (0-6) which a weekly schedule should run """
        return self.__schedule_week_day

    @schedule_week_day.setter
    def schedule_week_day(self, val):
        self.__schedule_week_day = val

    @property
    def schedule(self):
        """ The schedule when the report will run """
        return self.__schedule

    @schedule.setter
    def schedule(self, val):
        self.__schedule = val

    @property
    def dag_id(self):
        """ Returns a DAG ID based on the name of this report """
        return inflection.underscore(inflection.parameterize(f"rb status {self.name}"))

    @property
    def tests(self):
        """ The tests run in the report """
        return self.__tests

    @tests.setter
    def tests(self, val):
        self.__tests = val

    @property
    def is_paused(self):
        return models.DagModel.get_dagmodel(self.dag_id).is_paused

    def activate_dag(self):
        models.DagModel.get_dagmodel(self.dag_id).set_is_paused(False)

    def pause_dag(self):
        models.DagModel.get_dagmodel(self.dag_id).set_is_paused(True)

    def _trigger_dag(self, dag_id: str, dag_bag: DagBag, dag_run: DagRun):
        dag = dag_bag.get_dag(dag_id)  # prefetch dag if it is stored serialized

        if dag_id not in dag_bag.dags:
            raise DagNotFound(f"Dag id {dag_id} not found")

        execution_date = timezone.utcnow()

        run_id = f"rb_status_manual__{execution_date.isoformat()}"
        dag_run_id = dag_run.find(dag_id=dag_id, run_id=run_id)
        if dag_run_id:
            raise DagRunAlreadyExists(
                f"Run id {run_id} already exists for dag id {dag_id}"
            )

        dag.create_dagrun(
            run_id=run_id,
            execution_date=execution_date,
            state=State.RUNNING,
            external_trigger=True,
        )

    def trigger_dag(self):
        """
        Triggers execution of DAG interpreted from the report's dag_id

        _trigger_dag iterates through the class registry and looks
        For any model that has dag_id as an attribute and deletes
        all references to the specific dag_id

        :param dag_id: DAG ID
        :param dagbag: dagbag
        :param dagrun: empty dag run to be created
        """
        dag_model = DagModel.get_current(self.dag_id)
        if dag_model is None:
            raise DagNotFound(f"Dag id {self.dag_id} not found in DagModel")

        dagbag = DagBag(
            dag_folder=dag_model.fileloc,
            store_serialized_dags=conf.getboolean("core", "store_serialized_dags"),
        )
        dag_run = DagRun()
        self._trigger_dag(dag_id=self.dag_id, dag_bag=dagbag, dag_run=dag_run)

    @provide_session
    def delete_dag(self, keep_records_in_log: bool = True, session=None):
        dag = session.query(DagModel).filter(DagModel.dag_id == self.dag_id).first()
        if dag is None:
            raise DagNotFound(f"Dag id {self.dag_id} not found")

        # so explicitly removes serialized DAG here.
        if STORE_SERIALIZED_DAGS and SerializedDagModel.has_dag(
            dag_id=self.dag_id, session=session
        ):
            SerializedDagModel.remove_dag(dag_id=self.dag_id, session=session)

        # noinspection PyUnresolvedReferences,PyProtectedMember
        for model in models.base.Base._decl_class_registry.values():
            if hasattr(model, "dag_id"):
                if model.__name__:
                    print(model.__name__)
                if keep_records_in_log and model.__name__ == "Log":
                    continue
                cond = or_(
                    model.dag_id == self.dag_id, model.dag_id.like(self.dag_id + ".%")
                )
                session.query(model).filter(cond).delete(synchronize_session="fetch")

        # Delete entries in Import Errors table for a deleted DAG
        # This handles the case when the dag_id is changed in the file
        session.query(models.ImportError).filter(
            models.ImportError.filename == dag.fileloc
        ).delete(synchronize_session="fetch")

    @provide_session
    def delete_report_variable(self, report_prefix, session=None):
        """
        Deletes variable of the report
        """
        session.query(Variable).filter(
            Variable.key == (report_prefix + self.name)
        ).delete(synchronize_session="fetch")
