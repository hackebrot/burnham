# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import base64
import json
from dataclasses import dataclass
from typing import Any, List

import pytest
from google.cloud import bigquery

pytest_plugins: List[str] = ["plugins.store_results_in_bigquery"]


def pytest_addoption(parser):
    """Define custom CLI options."""
    burnham_group = parser.getgroup("burnham")
    burnham_group.addoption(
        "--run-id",
        action="store",
        dest="run_id",
        help="ID of the current test run",
        metavar="RUN_ID",
        type=str,
        required=True,
    )
    burnham_group.addoption(
        "--execution-timestamp",
        action="store",
        dest="execution_timestamp",
        help="Airflow execution timestamp of the current test run in ISO format",
        metavar="TIMESTAMP",
        type=str,
        required=True,
    )
    burnham_group.addoption(
        "--scenarios",
        action="store",
        dest="scenarios",
        help="base64 encoded test scenarios",
        metavar="SCENARIOS",
        type=str,
        required=True,
    )
    burnham_group.addoption(
        "--project-id",
        action="store",
        dest="project_id",
        help="BigQuery project ID",
        metavar="PROJECT_ID",
        type=str,
        required=True,
    )


@dataclass(frozen=True)
class Scenario:
    """Class that holds information about a specific test scenario."""

    name: str
    query: str
    want: List[List[Any]]


@dataclass(frozen=True)
class Run:
    """Class that holds information about the current test run."""

    identifier: str
    execution_timestamp: str
    scenarios: List[Scenario]


def pytest_configure(config):
    """Load test run information from custom CLI options."""

    if config.option.scenarios is not None:
        # telemetry-airflow encodes the test scenarios
        b64_decoded = base64.b64decode(config.option.scenarios)
        utf_decoded = b64_decoded.decode("utf-8")
        scenarios = json.loads(utf_decoded)

        config.burnham_run = Run(
            identifier=config.option.run_id,
            execution_timestamp=config.option.execution_timestamp,
            scenarios=[Scenario(**scenario) for scenario in scenarios],
        )


def pytest_generate_tests(metafunc):
    """Generate tests from test run information."""

    ids = []
    argvalues = []

    for scenario in metafunc.config.burnham_run.scenarios:
        ids.append(scenario.name)
        query_job_config = bigquery.QueryJobConfig(
            # The SQL query is expected to contain the following parameters
            # which get passed in as CLI options to burnham-bigquery
            query_parameters=[
                bigquery.ScalarQueryParameter(
                    "burnham_test_run", "STRING", metafunc.config.burnham_run.identifier
                ),
                bigquery.ScalarQueryParameter(
                    "burnham_execution_timestamp",
                    "STRING",
                    metafunc.config.burnham_run.execution_timestamp,
                ),
            ]
        )
        argvalues.append([query_job_config, scenario.query, scenario.want])

    metafunc.parametrize(["query_job_config", "query", "want"], argvalues, ids=ids)


@pytest.fixture(name="client", scope="session")
def fixture_client(request) -> bigquery.Client:
    """Return a BigQuery client."""
    return bigquery.Client(project=request.config.option.project_id)
