""" Utilities for validate containerized simulators

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2020-12-21
:Copyright: 2020, Center for Reproducible Biomedical Modeling
:License: MIT
"""

from .config import TERMINAL_COLORS
from .data_model import (TestCase, TestCaseResult,  # noqa: F401
                         TestCaseResultType, TestCaseWarning, SkippedTestCaseException, IgnoredTestCaseWarning,
                         OutputMedium)
from .test_case import cli
from .test_case import combine_archive
from .test_case import docker_image
from .test_case import published_project
from .test_case import sedml
import biosimulators_utils.simulator.io
import capturer
import collections
import datetime
import inspect
import sys
import termcolor
import warnings

__all__ = ['SimulatorValidator']


class SimulatorValidator(object):
    """ Validate that a Docker image for a simulator implements the BioSimulations simulator interface by
    checking that the image produces the correct outputs for one of more test cases (e.g., COMBINE archive)

    Attributes:
        specifications (:obj:`str` or :obj:`dict`): path or URL to the specifications of the simulator, or the specifications of the simulator
        cases (:obj:`collections.OrderedDict` of :obj:`types.ModuleType` to :obj:`TestCase`): groups of test cases
        verbose (:obj:`bool`): if :obj:`True`, display stdout/stderr from executing cases in real time
        output_medium (:obj:`OutputMedium`): environment where outputs will be sent
    """

    def __init__(self, specifications, case_ids=None, verbose=False, output_medium=OutputMedium.console):
        """
        Args:
            specifications (:obj:`str` or :obj:`dict`): path or URL to the specifications of the simulator, or the specifications of the simulator
            case_ids (:obj:`list` of :obj:`str`, optional): List of ids of test cases to verify. If :obj:`ids`
                is none, all test cases are verified.
            verbose (:obj:`bool`, optional): if :obj:`True`, display stdout/stderr from executing cases in real time
            output_medium (:obj:`OutputMedium`, optional): environment where outputs will be sent
        """
        # if necessary, get and validate specifications of simulator
        if isinstance(specifications, str):
            specifications = biosimulators_utils.simulator.io.read_simulator_specs(specifications)

        self.specifications = specifications
        self.verbose = verbose
        self.output_medium = output_medium

        self.cases = self.find_cases(ids=case_ids)

    def find_cases(self, ids=None):
        """ Find test cases

        Args:
            ids (:obj:`list` of :obj:`str`, optional): List of ids of test cases to verify. If :obj:`ids`
                is none, all test cases are verified.

        Returns:
            :obj:`collections.OrderedDict` of :obj:`types.ModuleType` to :obj:`TestCase`: groups of test cases
        """
        cases = collections.OrderedDict()

        # get cases involving curated published COMBINE/OMEX archives
        all_published_projects_test_cases, compatible_published_projects_test_cases = published_project.find_cases(
            self.specifications, output_medium=self.output_medium)

        # get Docker image cases
        suite_name = docker_image.__name__.replace('biosimulators_test_suite.test_case.', '')
        cases[suite_name] = self.find_cases_in_module(docker_image, compatible_published_projects_test_cases, ids=ids)

        # get command-line interface cases
        suite_name = cli.__name__.replace('biosimulators_test_suite.test_case.', '')
        cases[suite_name] = self.find_cases_in_module(cli, compatible_published_projects_test_cases, ids=ids)

        # get COMBINE archive test cases
        suite_name = combine_archive.__name__.replace('biosimulators_test_suite.test_case.', '')
        cases[suite_name] = self.find_cases_in_module(combine_archive, compatible_published_projects_test_cases, ids=ids)

        # get SED-ML cases
        suite_name = sedml.__name__.replace('biosimulators_test_suite.test_case.', '')
        cases[suite_name] = self.find_cases_in_module(sedml, compatible_published_projects_test_cases, ids=ids)

        # add cases involving published COMBINE/OMEX archives
        suite_name = published_project.__name__.replace('biosimulators_test_suite.test_case.', '')
        cases[suite_name] = []
        for case in all_published_projects_test_cases:
            if ids is None or case.id in ids:
                cases[suite_name].append(case)

        # warn if desired cases weren't found
        if ids is not None:
            found_case_ids = set()
            for suite_cases in cases.values():
                for case in suite_cases:
                    found_case_ids.add(case.id)

            missing_ids = set(ids).difference(found_case_ids)
            if missing_ids:
                warnings.warn('Some test case(s) were not found:\n  {}'.format('\n  '.join(sorted(missing_ids))), IgnoredTestCaseWarning)

        # return discovered cases
        return cases

    def find_cases_in_module(self, module, published_projects_test_cases, ids=None):
        """ Discover test cases in a module

        Args:
            module (:obj:`types.ModuleType`): module
            ids (:obj:`list` of :obj:`str`, optional): List of ids of test cases to verify. If :obj:`ids`
                is none, all test cases are verified.
            published_projects_test_cases (:obj:`list` of :obj:`published_project.PublishedProjectTestCase`): test cases involving
                executing curated COMBINE/OMEX archives

        Returns:
            :obj:`list` of :obj:`TestCase`: test cases
        """
        cases = []
        ignored_ids = []
        module_name = module.__name__.replace('biosimulators_test_suite.test_case.', '')
        for child_name in dir(module):
            child = getattr(module, child_name)
            if isinstance(child, type) and issubclass(child, TestCase) and not inspect.isabstract(child):
                id = module_name + '.' + child_name
                if ids is None or id in ids:
                    description = child.__doc__ or None
                    if description:
                        description_lines = (description
                                             .replace('\r', '')
                                             .replace('\n    ', '\n')
                                             .partition('\n\n')[0]
                                             .strip()
                                             .split('\n'))
                        description = ' '.join(line.strip() for line in description_lines) or None
                    if issubclass(child, published_project.SyntheticCombineArchiveTestCase):
                        case = child(id=id, description=description, output_medium=self.output_medium,
                                     published_projects_test_cases=published_projects_test_cases)
                    else:
                        case = child(id=id, description=description, output_medium=self.output_medium)
                    cases.append(case)
                else:
                    ignored_ids.append(id)

        if ignored_ids:
            warnings.warn('Some test case(s) were ignored:\n  {}'.format('\n  '.join(sorted(ignored_ids))), IgnoredTestCaseWarning)

        return cases

    def run(self):
        """ Validate that a Docker image for a simulator implements the BioSimulations simulator interface by
        checking that the image produces the correct outputs for test cases (e.g., COMBINE archive)

        Returns:
            :obj:`list` :obj:`TestCaseResult`: results of executing test cases
        """
        # print starting message
        n_cases = 0
        for suite_cases in self.cases.values():
            n_cases += len(suite_cases)
        print('Collected {} test cases.'.format(n_cases))

        # get start time
        start = datetime.datetime.now()

        # execute test cases and collect results
        results = []
        for suite_name, suite_cases in self.cases.items():
            print('\nExecuting {} {} tests ... {}'.format(len(suite_cases), suite_name, 'done' if not suite_cases else ''))
            for i_case, case in enumerate(suite_cases):
                print('  {}: {} ... '.format(i_case + 1, case.id), end='')
                sys.stdout.flush()

                result = self.eval_case(case)
                results.append(result)

                print(termcolor.colored(result.type.value, TERMINAL_COLORS[result.type.value]), end='')
                print(' (', end='')
                if result.warnings:
                    print(termcolor.colored(str(len(result.warnings)) + ' warnings, ', TERMINAL_COLORS['warned']), end='')
                print('{:.1f} s'.format(result.duration), end='')
                print(').')

        # get total duration
        duration = (datetime.datetime.now() - start).total_seconds()

        # print completion message
        print('\n{} tests completed in {:.1f} s'.format(n_cases, duration))

        # return results
        return results

    def eval_case(self, case):
        """ Evaluate a test case for a simulator

        Args:
            case (:obj:`TestCase`): test case

        Returns:
            :obj:`TestCaseResult`: test case result
        """
        start_time = datetime.datetime.now()

        with capturer.CaptureOutput(merged=True, relay=self.verbose) as captured:
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("ignore")
                warnings.simplefilter("always", TestCaseWarning)

                try:
                    case.eval(self.specifications)
                    type = TestCaseResultType.passed
                    exception = None

                except SkippedTestCaseException as caught_exception:
                    type = TestCaseResultType.skipped
                    exception = caught_exception

                except Exception as caught_exception:
                    type = TestCaseResultType.failed
                    exception = caught_exception

                duration = (datetime.datetime.now() - start_time).total_seconds()

                return TestCaseResult(
                    case=case,
                    type=type,
                    duration=duration,
                    exception=exception,
                    warnings=caught_warnings,
                    log=captured.get_text())

    @staticmethod
    def summarize_results(results):
        """ Get a summary of the results of a set of test cases

        Args:
            results (:obj:`list` :obj:`TestCaseResult`): results of executing test cases

        Returns:
            :obj:`tuple`

                * :obj:`str`: summary of results of test cases
                * :obj:`list` of :obj:`str`: details of failures
                * :obj:`list` of :obj:`str`: details of warnings
        """
        passed = []
        failed = []
        skipped = []
        warning_details = []
        failure_details = []
        for result in sorted(results, key=lambda result: result.case.id):
            if result.type == TestCaseResultType.passed:
                result_str = '  * `{}`\n'.format(result.case.id)
                passed.append(result_str)

            elif result.type == TestCaseResultType.failed:
                result_str = '  * `{}`\n'.format(result.case.id)
                failed.append(result_str)

                detail = ''
                detail += '`{}` ({:.1f} s)\n'.format(result.case.id, result.duration)
                detail += '\n'
                if result.case.description:
                    detail += '  {}\n'.format(result.case.description.replace('\n', '\n  '))
                    detail += '\n'
                detail += '  Exception:\n'
                detail += '\n'
                detail += '  ```\n'
                detail += '  {}\n'.format(str(result.exception).replace('\n', '\n  '))
                detail += '  ```\n'
                detail += '\n'
                detail += '  Log:\n'
                detail += '\n'
                detail += '  ```\n'
                detail += '  {}\n'.format(result.log.replace('\n', '\n  ') if result.log else '')
                detail += '  ```'
                failure_details.append(detail)

            elif result.type == TestCaseResultType.skipped:
                result_str = '  * `{}`\n'.format(result.case.id)
                skipped.append(result_str)

            if result.warnings:
                detail = ''
                detail += '`{}` ({:.1f} s)\n'.format(result.case.id, result.duration)
                detail += '\n'
                if result.case.description:
                    detail += '  {}\n'.format(result.case.description.replace('\n', '\n  '))
                    detail += '\n'
                detail += '  Warnings:\n'
                for warning in result.warnings:
                    detail += '\n'
                    detail += '  ```\n'
                    detail += '  {}\n'.format(str(warning.message).replace('\n', '\n  '))
                    detail += '  ```\n'
                detail += '\n'
                detail += '  Log:\n'
                detail += '\n'
                detail += '  ```\n'
                detail += '  {}\n'.format(result.log.replace('\n', '\n  ') if result.log else '')
                detail += '  ```'
                warning_details.append(detail)

        return (
            '\n'.join([
                '* Executed {} test cases\n'.format(len(results)),
                '* Passed {} test cases{}\n{}'.format(len(passed), ':' if passed else '', ''.join(passed)),
                '* Failed {} test cases{}\n{}'.format(len(failed), ':' if failed else '', ''.join(failed)),
                '* Skipped {} test cases{}\n{}'.format(len(skipped), ':' if skipped else '', ''.join(skipped)),
            ]).strip(),
            failure_details,
            warning_details,
        )
