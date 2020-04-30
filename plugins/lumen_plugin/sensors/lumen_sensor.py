from airflow.sensors.base_sensor_operator import BaseSensorOperator
from airflow.utils.decorators import apply_defaults
from airflow.models.taskinstance import TaskInstance
from airflow.utils.db import create_session
from airflow.utils.state import State
from sqlalchemy.orm.exc import NoResultFound


class LumenSensor(BaseSensorOperator):
    """
    This operator will check whether a test
    (task_instance) succeeded or failed, and
    will reflect that result as it's state.

    :param test_name: Name of task_instance to be tested
    :type test_name: str
    """

    template_fields = (
        "test_dag_id",
        "test_task_id"
    )

    @apply_defaults
    def __init__(
        self,
        test_dag_id,
        test_task_id,
        *args,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.test_dag_id = test_dag_id
        self.test_task_id = test_task_id

    def poke(self, context):
        self.log.info(
            f"Querying for {self.test_dag_id}.{self.test_task_id}'s result..."
        )
        # Query metadata and save to test_result
        with create_session() as curr_session:
            ti = curr_session.query(TaskInstance).filter(
                TaskInstance.task_id == self.test_task_id,
                TaskInstance.dag_id == self.test_dag_id,
            ).order_by(TaskInstance.execution_date.desc()).first()

            if not ti:
                raise NoResultFound

            state = ti.state
            terminal_failure_states = [
                State.FAILED, State.UPSTREAM_FAILED,
                State.SHUTDOWN, State.REMOVED
            ]
            terminal_success_states = [State.SUCCESS, State.SKIPPED]

            self.log.info(
                f"{self.test_dag_id}.{self.test_task_id} is in state {ti.state}"
            )

            if state in terminal_failure_states:
                self.log.error('Test was in a terminal failed state')
                raise ValueError()
            if state in terminal_success_states:
                return True
            else:
                return False