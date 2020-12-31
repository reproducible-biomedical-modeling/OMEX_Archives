""" Methods for testing that simulators support the features of SED-ML

:Author: Jonathan Karr <karr@mssm.edu>
:Date: 2020-12-21
:Copyright: 2020, Center for Reproducible Biomedical Modeling
:License: MIT
"""
from ..exceptions import InvalidOuputsException
from ..warnings import InvalidOuputsWarning
from .published_project import SingleMasterSedDocumentCombineArchiveTestCase, UniformTimeCourseTestCase
from biosimulators_utils.combine.data_model import CombineArchive  # noqa: F401
from biosimulators_utils.report.io import ReportReader
from biosimulators_utils.sedml.data_model import (SedDocument, Report, DataSet,  # noqa: F401
                                                  DataGenerator, DataGeneratorVariable,
                                                  UniformTimeCourseSimulation,
                                                  DataGeneratorVariableSymbol)
import copy
import os
import warnings

__all__ = [
    'SimulatorSupportsModelsSimulationsTasksDataGeneratorsAndReports',
    'SimulatorSupportsMultipleTasksPerSedDocument',
    'SimulatorSupportsMultipleReportsPerSedDocument',
    'SimulatorSupportsUniformTimeCoursesWithNonZeroOutputStartTimes',
    'SimulatorSupportsUniformTimeCoursesWithNonZeroInitialTimes',
]


class SimulatorSupportsModelsSimulationsTasksDataGeneratorsAndReports(SingleMasterSedDocumentCombineArchiveTestCase):
    """ Test that a simulator supports the core elements of SED: models, simulations, tasks, data generators for
    individual variables, and reports
    """

    def eval_outputs(self, specifications, synthetic_archive, synthetic_sed_docs, outputs_dir):
        """ Test that the expected outputs were created for the synthetic archive

        Args:
            specifications (:obj:`dict`): specifications of the simulator to validate
            synthetic_archive (:obj:`CombineArchive`): synthetic COMBINE/OMEX archive for testing the simulator
            synthetic_sed_docs (:obj:`dict` of :obj:`str` to :obj:`SedDocument`): map from the location of each SED
                document in the synthetic archive to the document
            outputs_dir (:obj:`str`): directory that contains the outputs produced from the execution of the synthetic archive

        Returns:
            :obj:`bool`: :obj:`True`, if succeeded without warnings
        """
        has_warnings = False

        # reports
        try:
            report_ids = ReportReader().get_ids(outputs_dir)
        except Exception:
            report_ids = []

        expected_report_ids = set()
        for doc_location, doc in synthetic_sed_docs.items():
            doc_id = os.path.relpath(doc_location, './')
            for output in doc.outputs:
                if isinstance(output, Report):
                    expected_report_ids.add(os.path.join(doc_id, output.id))

        missing_report_ids = expected_report_ids.difference(set(report_ids))
        extra_report_ids = set(report_ids).difference(expected_report_ids)

        if missing_report_ids:
            raise InvalidOuputsException('Simulator did not produce the following reports:\n  - {}'.format(
                '\n  - '.join(sorted('`' + id + '`' for id in missing_report_ids))
            ))

        if extra_report_ids:
            msg = 'Simulator produced extra reports:\n  - {}'.format(
                '\n  - '.join(sorted('`' + id + '`' for id in extra_report_ids)))
            warnings.warn(msg, InvalidOuputsWarning)
            has_warnings = True

        # data sets
        expected_data_set_labels = set()
        data_set_labels = set()
        for doc_location, doc in synthetic_sed_docs.items():
            doc_id = os.path.relpath(doc_location, './')
            for output in doc.outputs:
                if isinstance(output, Report):
                    for data_set in output.data_sets:
                        expected_data_set_labels.add(os.path.join(doc_id, output.id, data_set.label))

                    results = ReportReader().run(outputs_dir, os.path.join(doc_id, output.id))
                    data_set_labels.update(set(os.path.join(doc_id, output.id, label) for label in results.index))

        missing_data_set_labels = expected_data_set_labels.difference(set(data_set_labels))
        extra_data_set_labels = set(data_set_labels).difference(expected_data_set_labels)

        if missing_data_set_labels:
            raise InvalidOuputsException('Simulator did not produce the following data sets:\n  - {}'.format(
                '\n  - '.join(sorted('`' + label + '`' for label in missing_data_set_labels))
            ))

        if extra_data_set_labels:
            msg = 'Simulator produced extra data sets:\n  - {}'.format(
                '\n  - '.join(sorted('`' + label + '`' for label in extra_data_set_labels)))
            warnings.warn(msg, InvalidOuputsWarning)
            has_warnings = True

        return not has_warnings


class SimulatorSupportsMultipleTasksPerSedDocument(SingleMasterSedDocumentCombineArchiveTestCase):
    """ Test that a simulator supports multiple tasks per SED document

    Attributes:
        _expected_reports (:obj:`list` of :obj:`tuple` of :obj:`str`): list of pairs of
            original reports and their expected duplicates
    """

    def build_synthetic_archive(self, curated_archive, curated_archive_dir, curated_sed_docs):
        """ Generate a synthetic archive with a copy of each task and each report

        Args:
            curated_archive (:obj:`CombineArchive`): curated COMBINE/OMEX archive
            curated_archive_dir (:obj:`str`): directory with the contents of the curated COMBINE/OMEX archive
            curated_sed_docs (:obj:`dict` of :obj:`str` to :obj:`SedDocument`): map from locations to
                SED documents in curated archive

        Returns:
            :obj:`tuple`:

                * :obj:`CombineArchive`: synthetic COMBINE/OMEX archive for testing the simulator
                * :obj:`dict` of :obj:`str` to :obj:`SedDocument`: map from locations to
                  SED documents in synthetic archive
        """
        curated_archive, curated_sed_docs = super(SimulatorSupportsMultipleTasksPerSedDocument, self).build_synthetic_archive(
            curated_archive, curated_archive_dir, curated_sed_docs)

        # get a suitable SED document to modify
        location = list(curated_sed_docs.keys())[0]
        doc_id = os.path.relpath(location, './')
        sed_doc = curated_sed_docs[location]

        # duplicate tasks and reports
        copy_tasks = {}
        for task in list(sed_doc.tasks):
            copy_task = copy.copy(task)
            copy_task.id += '__test_suite_copy'
            sed_doc.tasks.append(copy_task)
            copy_tasks[task.id] = copy_task

        self._expected_reports = []
        copy_data_gens = {}
        for output in list(sed_doc.outputs):
            if isinstance(output, Report):
                copy_output = Report(id=output.id + '__test_suite_copy')
                sed_doc.outputs.append(copy_output)

                self._expected_reports.append((
                    os.path.join(doc_id, output.id),
                    os.path.join(doc_id, copy_output.id)))

                for data_set in output.data_sets:
                    copy_data_set = DataSet(id=data_set.id + '__test_suite_copy', label=data_set.label)
                    copy_output.data_sets.append(copy_data_set)

                    data_gen = data_set.data_generator
                    copy_data_gen_id = data_gen.id + '__test_suite_copy'
                    copy_data_gen = copy_data_gens.get(copy_data_gen_id, None)
                    if not copy_data_gen:
                        copy_data_gen = DataGenerator(id=copy_data_gen_id, parameters=data_gen.parameters, math=data_gen.math)
                        sed_doc.data_generators.append(copy_data_gen)

                        for var in data_set.data_generator.variables:
                            copy_var = DataGeneratorVariable(id=var.id, target=var.target, symbol=var.symbol, model=var.model)
                            copy_var.task = copy_tasks[var.task.id]
                            copy_data_gen.variables.append(copy_var)
                    copy_data_set.data_generator = copy_data_gen

        # return modified SED document
        return (curated_archive, curated_sed_docs)

    def eval_outputs(self, specifications, synthetic_archive, synthetic_sed_docs, outputs_dir):
        """ Test that the expected outputs were created for the synthetic archive

        Args:
            specifications (:obj:`dict`): specifications of the simulator to validate
            synthetic_archive (:obj:`CombineArchive`): synthetic COMBINE/OMEX archive for testing the simulator
            synthetic_sed_docs (:obj:`dict` of :obj:`str` to :obj:`SedDocument`): map from the location of each SED
                document in the synthetic archive to the document
            outputs_dir (:obj:`str`): directory that contains the outputs produced from the execution of the synthetic archive
        """
        try:
            report_ids = ReportReader().get_ids(outputs_dir)
        except Exception:
            report_ids = []

        missing_reports = []
        for report_loc, copy_report_loc in self._expected_reports:
            if report_loc not in report_ids:
                missing_reports.append(report_loc)
            if copy_report_loc not in report_ids:
                missing_reports.append(copy_report_loc)

        if missing_reports:
            raise ValueError('Reports for duplicate tasks were not generated:\n  {}'.format(
                '\n  '.join(sorted(missing_reports))))


class SimulatorSupportsMultipleReportsPerSedDocument(SingleMasterSedDocumentCombineArchiveTestCase):
    """ Test that a simulator supports multiple reports per SED document """

    def build_synthetic_archive(self, curated_archive, curated_archive_dir, curated_sed_docs):
        """ Generate a synthetic archive with a copy of each task and each report

        Args:
            curated_archive (:obj:`CombineArchive`): curated COMBINE/OMEX archive
            curated_archive_dir (:obj:`str`): directory with the contents of the curated COMBINE/OMEX archive
            curated_sed_docs (:obj:`dict` of :obj:`str` to :obj:`SedDocument`): map from locations to
                SED documents in curated archive

        Returns:
            :obj:`tuple`:

                * :obj:`CombineArchive`: synthetic COMBINE/OMEX archive for testing the simulator
                * :obj:`dict` of :obj:`str` to :obj:`SedDocument`: map from locations to
                  SED documents in synthetic archive
        """
        curated_archive, curated_sed_docs = super(SimulatorSupportsMultipleReportsPerSedDocument, self).build_synthetic_archive(
            curated_archive, curated_archive_dir, curated_sed_docs)

        # get a suitable SED document to modify
        sed_doc = list(curated_sed_docs.values())[0]

        # divide data sets between two reports
        original_data_sets = sed_doc.outputs[0].data_sets
        sed_doc.outputs = [
            Report(id='report_1'),
            Report(id='report_2'),
        ]
        for i_dataset, data_set in enumerate(original_data_sets):
            sed_doc.outputs[i_dataset % 2].data_sets.append(data_set)

        # return modified SED document
        return (curated_archive, curated_sed_docs)

    def eval_outputs(self, specifications, synthetic_archive, synthetic_sed_docs, outputs_dir):
        """ Test that the expected outputs were created for the synthetic archive

        Args:
            specifications (:obj:`dict`): specifications of the simulator to validate
            synthetic_archive (:obj:`CombineArchive`): synthetic COMBINE/OMEX archive for testing the simulator
            synthetic_sed_docs (:obj:`dict` of :obj:`str` to :obj:`SedDocument`): map from the location of each SED
                document in the synthetic archive to the document
            outputs_dir (:obj:`str`): directory that contains the outputs produced from the execution of the synthetic archive
        """
        has_warnings = False

        try:
            report_ids = ReportReader().get_ids(outputs_dir)
        except Exception:
            report_ids = []

        doc_location = os.path.relpath(list(synthetic_sed_docs.keys())[0], './')
        expected_report_ids = set([os.path.join(doc_location, 'report_1'), os.path.join(doc_location, 'report_2')])

        missing_report_ids = expected_report_ids.difference(set(report_ids))
        extra_report_ids = set(report_ids).difference(expected_report_ids)

        if missing_report_ids:
            raise InvalidOuputsException('Simulator did not produce the following reports:\n  - {}'.format(
                '\n  - '.join(sorted('`' + id + '`' for id in missing_report_ids))
            ))

        if extra_report_ids:
            msg = 'Simulator produced extra reports:\n  - {}'.format(
                '\n  - '.join(sorted('`' + id + '`' for id in extra_report_ids)))
            warnings.warn(msg, InvalidOuputsWarning)
            has_warnings = True

        return not has_warnings


class SimulatorSupportsUniformTimeCoursesWithNonZeroOutputStartTimes(UniformTimeCourseTestCase):
    """ Test that a simulator supports multiple reports per SED document """

    def modify_simulation(self, simulation):
        """ Modify a simulation

        Args:
            simulation (:obj:`UniformTimeCourseSimulation`): simulation
        """
        simulation.output_start_time = simulation.output_end_time / 2
        simulation.number_of_points = int(simulation.number_of_points / 2)


class SimulatorSupportsUniformTimeCoursesWithNonZeroInitialTimes(UniformTimeCourseTestCase):
    """ Test that a simulator supports multiple reports per SED document """

    def modify_simulation(self, simulation):
        """ Modify a simulation

        Args:
            simulation (:obj:`UniformTimeCourseSimulation`): simulation
        """
        simulation.initial_time = simulation.output_end_time / 2
        simulation.output_start_time = simulation.output_end_time / 2
        simulation.number_of_points = int(simulation.number_of_points / 2)
