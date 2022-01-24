# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Tuple

import click
from glean import Glean
from glean.config import Configuration

from burnham import __title__, __version__, metrics, pings
from burnham.exceptions import BurnhamError
from burnham.missions import Mission, complete_mission, missions_by_identifier
from burnham.space_travel import Discovery, SporeDrive, WarpDrive

logger = logging.getLogger(__name__)


class MissionParamType(click.ParamType):
    """Custom Param Type for space-travel missions."""

    def convert(self, value, param, ctx) -> Mission:
        """Look up Mission by its identifier."""
        identifier = click.STRING(value, param, ctx)

        if identifier not in missions_by_identifier:
            raise click.BadParameter(
                f'Unknown mission identifier "{identifier}"',
                ctx,
                param,
            )

        return missions_by_identifier[identifier]


@click.command()
@click.version_option(
    __version__,
    "-V",
    "--version",
)
@click.option(
    "-v",
    "--verbose",
    help="Print debug information to the console",
    type=bool,
    default=False,
    is_flag=True,
    envvar="BURNHAM_VERBOSE",
)
@click.option(
    "-r",
    "--test-run",
    help="ID of the current test run",
    type=str,
    required=True,
    envvar="BURNHAM_TEST_RUN",
)
@click.option(
    "-n",
    "--test-name",
    help="Name of the current test",
    type=str,
    required=True,
    envvar="BURNHAM_TEST_NAME",
)
@click.option(
    "-p",
    "--platform",
    help="Data Platform URL",
    type=str,
    required=True,
    envvar="BURNHAM_PLATFORM_URL",
)
@click.option(
    "-s",
    "--spore-drive",
    help="Interface for the spore-drive technology",
    type=click.Choice(["tardigrade", "tardigrade-dna"]),
    required=False,
    envvar="BURNHAM_SPORE_DRIVE",
)
@click.option(
    "-t/-T",
    "--enable-telemetry/--disable-telemetry",
    help="Enable/Disable telemetry submission with Glean",
    type=bool,
    default=True,
    is_flag=True,
    envvar="BURNHAM_TELEMETRY",
)
@click.argument(
    "missions",
    envvar="BURNHAM_MISSIONS",
    type=MissionParamType(),
    nargs=-1,
    required=True,
)
def burnham(
    verbose: bool,
    test_run: str,
    test_name: str,
    enable_telemetry: bool,
    platform: str,
    spore_drive: str,
    missions: Tuple[Mission],
) -> None:
    """Travel through space and complete missions with the Discovery crew.

    If telemetry is enabled, measure, collect, and submit non-personal
    information to the specified data platform with Glean.
    """

    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    Glean.initialize(
        application_id=__title__,
        application_version=__version__,
        upload_enabled=enable_telemetry is True,
        data_dir=Path(TemporaryDirectory().name),
        configuration=Configuration(server_endpoint=platform),
        log_level=logging.DEBUG
    )

    metrics.test.run.set(test_run)
    metrics.test.name.set(test_name)

    space_ship = Discovery(
        warp_drive=WarpDrive(),
        spore_drive=SporeDrive(branch=spore_drive, active=spore_drive is not None),
    )
    pings.space_ship_ready.submit()

    try:
        for mission in missions:
            complete_mission(space_ship=space_ship, mission=mission)

            # When mission "MISSION H: DISABLE GLEAN UPLOAD" disables the Glean
            # SDK ping upload all pending events, metrics and pings are
            # cleared, except for first_run_date. We need to restore values for
            # test.run and test.name after re-enabling ping upload, so that we
            # can properly correlate new pings with the test scenario.
            if mission.identifier == "MISSION I: ENABLE GLEAN UPLOAD":
                metrics.test.run.set(test_run)
                metrics.test.name.set(test_name)

        secs = 5
        logger.info("All missions completed.")
        logger.info(f" Waiting {secs}s for telemetry to be sent.")
        time.sleep(secs)

    except BurnhamError as err:
        click.echo(f"Error: {err}", err=True)
        sys.exit(1)
