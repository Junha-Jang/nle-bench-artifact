"""Tests for E1-E5 visualization integration (Phase 4)."""

import pytest

from nlebench.metrics.error_taxonomy import ErrorAnalysis, ErrorCategory, ErrorClassification
from nlebench.analysis.visualization import (
    generate_error_taxonomy_chart,
    generate_qualitative_examples,
)


class TestErrorTaxonomyChart:
    """Test generate_error_taxonomy_chart()."""

    def test_empty_analysis(self):
        analysis = ErrorAnalysis(total_errors=0)
        result = generate_error_taxonomy_chart(analysis)
        assert "No errors" in result

    def test_with_errors(self):
        analysis = ErrorAnalysis(
            total_errors=10,
            by_category={"E1": 4, "E2": 2, "E3": 1, "E4": 2, "E5": 1, "E5a": 0, "E5b": 0, "E5c": 0, "E5d": 0},
        )
        result = generate_error_taxonomy_chart(analysis)
        assert "Error Taxonomy" in result
        assert "Overall:" in result
        assert "Parameter" in result

    def test_by_level_display(self):
        analysis = ErrorAnalysis(
            total_errors=5,
            by_category={"E1": 3, "E2": 1, "E3": 0, "E4": 1, "E5": 0, "E5a": 0, "E5b": 0, "E5c": 0, "E5d": 0},
            by_level={
                "L1": {"E1": 2, "E2": 0, "E3": 0, "E4": 1, "E5": 0, "E5a": 0, "E5b": 0, "E5c": 0, "E5d": 0},
                "L2": {"E1": 1, "E2": 1, "E3": 0, "E4": 0, "E5": 0, "E5a": 0, "E5b": 0, "E5c": 0, "E5d": 0},
            },
        )
        result = generate_error_taxonomy_chart(analysis)
        assert "By Level:" in result
        assert "L1:" in result
        assert "L2:" in result


class TestQualitativeExamples:
    """Test generate_qualitative_examples()."""

    def test_empty_classifications(self):
        analysis = ErrorAnalysis(total_errors=0)
        result = generate_qualitative_examples(analysis)
        assert "No failures" in result

    def test_with_classifications(self):
        analysis = ErrorAnalysis(
            total_errors=3,
            classifications=[
                ErrorClassification(
                    category=ErrorCategory.E1_PARAMETER,
                    constraint_name="required:caption.text.equals",
                    detail="expected='hello', got='world'",
                ),
                ErrorClassification(
                    category=ErrorCategory.E4_OMISSION,
                    constraint_name="required:captions.exists",
                ),
                ErrorClassification(
                    category=ErrorCategory.E5_SIDE_EFFECT,
                    constraint_name="ovr:unintended_change",
                    detail="OVR=0.500",
                ),
            ],
        )
        result = generate_qualitative_examples(analysis)
        assert "E1 Parameter Error" in result
        assert "caption.text.equals" in result
        assert "E4 Omission Error" in result
        assert "E5 Side Effect" in result

    def test_max_per_category(self):
        classifications = [
            ErrorClassification(
                category=ErrorCategory.E1_PARAMETER,
                constraint_name=f"field_{i}.equals",
            )
            for i in range(5)
        ]
        analysis = ErrorAnalysis(total_errors=5, classifications=classifications)
        result = generate_qualitative_examples(analysis, max_per_category=2)
        assert "and 3 more" in result


class TestReportGeneratorErrorIntegration:
    """Test that ReportGenerator exposes error_analysis."""

    def test_error_analysis_property(self):
        from nlebench.models import ExecutionResult, ValidationResult
        from nlebench.analysis.report_generator import ReportGenerator

        results = [
            ExecutionResult(
                scenario_id="L1_caption_001",
                run_number=0,
                success=False,
                validation=ValidationResult(
                    tsr=False,
                    csr=True,
                    ovr=0.0,
                    failed_constraints=["required:caption.text.equals"],
                ),
            ),
        ]
        gen = ReportGenerator(results)
        ea = gen.error_analysis
        assert ea.total_errors > 0
        assert ea.by_category["E1"] > 0
