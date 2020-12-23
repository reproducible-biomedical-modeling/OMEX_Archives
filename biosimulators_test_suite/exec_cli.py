""" Program for validating that simulation tools are consistent with the BioSimulators standards

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2020-12-22
:Copyright: 2020, BioSimulators Team
:License: MIT
"""

from biosimulators_test_suite.data_model import TestCaseResultType
import biosimulators_test_suite.exec_core
import cement


class BaseController(cement.Controller):
    """ Base controller for command line application """

    class Meta:
        label = 'base'
        description = "Validates that a simulation tool is consistent with the BioSimulators standards"
        help = "Validates that a simulation tool is consistent with the BioSimulators standards"
        arguments = [
            (['specifications'], dict(
                type=str,
                help='Path or URL to the specifications of the simulator',
            )),
            (['-c', '--combine-case'], dict(
                type=str,
                nargs='+',
                default=None,
                dest='combine_archive_case_ids',
                help=(
                    "Ids of COMBINE archive test cases of evaluate (e.g., "
                      "'sbml-core/Caravagna-J-Theor-Biol-2010-tumor-suppressive-oscillations'). "
                      "Default: evaluate all test cases"
                ),
            )),
            (['--verbose'], dict(
                action='store_true',
                help="If set, print the stdout and stderr of the execution of the tests in real time.",
            )),
            (['-v', '--version'], dict(
                action='version',
                version=biosimulators_test_suite.__version__,
            )),
        ]

    @cement.ex(hide=True)
    def _default(self):
        args = self.app.pargs
        try:
            validator = biosimulators_test_suite.exec_core.SimulatorValidator(
                combine_archive_case_ids=args.combine_archive_case_ids,
                verbose=args.verbose)
            results = validator.run(args.specifications)
            summary, failure_details = validator.summarize_results(results)
            print('=============== SUMMARY ===============')
            print(summary + '\n')
            if failure_details:
                print('=============== FAILURES ===============')
                print(failure_details)
        except Exception as exception:
            raise SystemExit(str(exception))

        any_passed = False
        failed = False
        for result in results:
            if result.type == TestCaseResultType.passed:
                any_passed = True
            elif result.type == TestCaseResultType.failed:
                failed = True

        if failed:
            exit(1)
        if not any_passed:
            exit(3)


class App(cement.App):
    """ Command line application """
    class Meta:
        label = 'biosimulators-test-suite'
        base_controller = 'base'
        handlers = [
            BaseController,
        ]


def main():
    with App() as app:
        app.run()