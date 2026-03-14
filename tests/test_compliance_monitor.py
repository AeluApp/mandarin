"""Tests for mandarin.openclaw.compliance_monitor — surfaces, frameworks, calendar, impact assessment."""

import unittest
from datetime import datetime

from mandarin.openclaw.compliance_monitor import (
    ActionItem,
    AeluComplianceSurface,
    ComplianceChecker,
    ComplianceMonitor,
    ComplianceReport,
    ComplianceSurface,
    FeedSource,
    ImpactAssessment,
    ImpactAssessor,
    RegulatoryFeedSource,
    RegulatoryFramework,
    SurfaceAssessment,
    _REGULATORY_CALENDAR,
    _SURFACES,
)


# ── Enum coverage ─────────────────────────────────────────

class TestRegulatoryFrameworkEnum(unittest.TestCase):
    def test_all_11_frameworks(self):
        expected = {
            "eu_ai_act", "gdpr", "ferpa", "coppa", "cpra",
            "ftc_ai", "state_ai_laws", "nist_ai_rmf",
            "unesco_ai_ethics", "oecd_ai_principles", "uk_ai_regulation",
        }
        actual = {f.value for f in RegulatoryFramework}
        self.assertEqual(expected, actual)
        self.assertEqual(len(RegulatoryFramework), 11)

    def test_framework_names(self):
        expected_names = [
            "EU_AI_ACT", "GDPR", "FERPA", "COPPA", "CPRA", "FTC_AI",
            "STATE_AI_LAWS", "NIST_AI_RMF", "UNESCO_AI_ETHICS",
            "OECD_AI_PRINCIPLES", "UK_AI_REGULATION",
        ]
        for name in expected_names:
            self.assertTrue(hasattr(RegulatoryFramework, name), f"Missing: {name}")


# ── Dataclass construction ────────────────────────────────

class TestComplianceSurface(unittest.TestCase):
    def test_construction(self):
        cs = ComplianceSurface(
            "test_area", "desc",
            [RegulatoryFramework.GDPR], "medium",
            ["control1"], ["data_type1"],
        )
        self.assertEqual(cs.area, "test_area")
        self.assertEqual(cs.risk_level, "medium")


class TestFeedSource(unittest.TestCase):
    def test_defaults(self):
        fs = FeedSource("name", "url", "rss", RegulatoryFramework.GDPR)
        self.assertEqual(fs.check_frequency_hours, 24)

    def test_custom_frequency(self):
        fs = FeedSource("name", "url", "scrape", RegulatoryFramework.FERPA, 168)
        self.assertEqual(fs.check_frequency_hours, 168)


class TestActionItem(unittest.TestCase):
    def test_defaults(self):
        ai = ActionItem("title", "desc", RegulatoryFramework.GDPR, "high")
        self.assertIsNone(ai.deadline)
        self.assertEqual(ai.assigned_to, "owner")

    def test_full_construction(self):
        ai = ActionItem("t", "d", RegulatoryFramework.COPPA, "critical",
                         deadline="2026-06-01", assigned_to="legal")
        self.assertEqual(ai.deadline, "2026-06-01")
        self.assertEqual(ai.assigned_to, "legal")


class TestSurfaceAssessment(unittest.TestCase):
    def test_defaults(self):
        cs = ComplianceSurface("a", "d", [], "low", [], [])
        sa = SurfaceAssessment(surface=cs, status="compliant")
        self.assertEqual(sa.gaps, [])
        self.assertEqual(sa.recommendations, [])


class TestComplianceReport(unittest.TestCase):
    def test_auto_timestamp(self):
        cr = ComplianceReport(overall_status="compliant")
        self.assertNotEqual(cr.last_checked, "")
        datetime.strptime(cr.last_checked, "%Y-%m-%d %H:%M:%S")

    def test_custom_timestamp(self):
        cr = ComplianceReport(overall_status="compliant",
                               last_checked="2026-01-01 00:00:00")
        self.assertEqual(cr.last_checked, "2026-01-01 00:00:00")


class TestImpactAssessment(unittest.TestCase):
    def test_construction(self):
        ia = ImpactAssessment(
            affects_aelu=True, impact_level="high",
            affected_surfaces=["audio_recordings"],
            required_changes=["review"], timeline="30 days",
            confidence=0.8,
        )
        self.assertTrue(ia.affects_aelu)
        self.assertEqual(ia.impact_level, "high")


# ── 10 compliance surfaces ────────────────────────────────

class TestSurfacesData(unittest.TestCase):
    def test_exactly_10_surfaces(self):
        self.assertEqual(len(_SURFACES), 10)

    def test_all_surface_areas(self):
        areas = {s.area for s in _SURFACES}
        expected = {
            "learner_data_collection", "audio_recordings", "ai_generated_content",
            "learning_analytics", "institutional_data", "payment_processing",
            "marketing_emails", "childrens_data", "cross_border_transfer",
            "automated_decisions",
        }
        self.assertEqual(areas, expected)

    def test_all_surfaces_have_frameworks(self):
        for s in _SURFACES:
            self.assertGreater(len(s.frameworks), 0,
                               f"Surface {s.area} has no frameworks")

    def test_all_surfaces_have_controls(self):
        for s in _SURFACES:
            self.assertGreater(len(s.current_controls), 0,
                               f"Surface {s.area} has no controls")

    def test_all_surfaces_have_data_types(self):
        for s in _SURFACES:
            self.assertGreater(len(s.data_types), 0,
                               f"Surface {s.area} has no data types")

    def test_risk_levels_valid(self):
        for s in _SURFACES:
            self.assertIn(s.risk_level, ("low", "medium", "high"),
                          f"Surface {s.area} has invalid risk level")

    def test_high_risk_surfaces(self):
        high = [s for s in _SURFACES if s.risk_level == "high"]
        areas = {s.area for s in high}
        self.assertIn("audio_recordings", areas)
        self.assertIn("institutional_data", areas)


# ── AeluComplianceSurface ────────────────────────────────

class TestAeluComplianceSurface(unittest.TestCase):
    def setUp(self):
        self.acs = AeluComplianceSurface()

    def test_get_surfaces(self):
        surfaces = self.acs.get_surfaces()
        self.assertEqual(len(surfaces), 10)

    def test_get_by_framework_gdpr(self):
        gdpr_surfaces = self.acs.get_by_framework(RegulatoryFramework.GDPR)
        self.assertGreater(len(gdpr_surfaces), 0)
        for s in gdpr_surfaces:
            self.assertIn(RegulatoryFramework.GDPR, s.frameworks)

    def test_get_by_framework_ferpa(self):
        ferpa_surfaces = self.acs.get_by_framework(RegulatoryFramework.FERPA)
        self.assertGreater(len(ferpa_surfaces), 0)
        areas = {s.area for s in ferpa_surfaces}
        self.assertIn("institutional_data", areas)

    def test_get_by_framework_coppa(self):
        coppa = self.acs.get_by_framework(RegulatoryFramework.COPPA)
        areas = {s.area for s in coppa}
        self.assertIn("childrens_data", areas)

    def test_get_high_risk(self):
        high = self.acs.get_high_risk()
        self.assertGreater(len(high), 0)
        for s in high:
            self.assertEqual(s.risk_level, "high")


# ── RegulatoryFeedSource ─────────────────────────────────

class TestRegulatoryFeedSource(unittest.TestCase):
    def setUp(self):
        self.rfs = RegulatoryFeedSource()

    def test_sources_exist(self):
        sources = self.rfs.get_sources()
        self.assertGreater(len(sources), 15)

    def test_all_sources_have_url(self):
        for s in self.rfs.get_sources():
            self.assertTrue(s.url, f"Source {s.name} has no URL")

    def test_all_sources_have_type(self):
        for s in self.rfs.get_sources():
            self.assertIn(s.feed_type, ("rss", "api", "scrape"),
                          f"Source {s.name} has invalid feed_type")

    def test_get_by_framework_eu_ai_act(self):
        eu_sources = self.rfs.get_by_framework(RegulatoryFramework.EU_AI_ACT)
        self.assertGreater(len(eu_sources), 0)

    def test_get_by_framework_ftc(self):
        ftc_sources = self.rfs.get_by_framework(RegulatoryFramework.FTC_AI)
        self.assertGreater(len(ftc_sources), 0)

    def test_multiple_frameworks_covered(self):
        frameworks = {s.framework for s in self.rfs.get_sources()}
        self.assertGreaterEqual(len(frameworks), 5)


# ── Regulatory calendar ──────────────────────────────────

class TestRegulatoryCalendar(unittest.TestCase):
    def test_calendar_entries_exist(self):
        self.assertGreater(len(_REGULATORY_CALENDAR), 5)

    def test_all_entries_have_required_fields(self):
        for entry in _REGULATORY_CALENDAR:
            self.assertIn("framework", entry)
            self.assertIn("event", entry)
            self.assertIn("date", entry)
            self.assertIn("status", entry)

    def test_dates_valid_format(self):
        for entry in _REGULATORY_CALENDAR:
            datetime.strptime(entry["date"], "%Y-%m-%d")

    def test_statuses_valid(self):
        valid = {"passed", "upcoming", "pending", "planned"}
        for entry in _REGULATORY_CALENDAR:
            self.assertIn(entry["status"], valid,
                          f"Calendar entry has invalid status: {entry['status']}")

    def test_eu_ai_act_dates(self):
        eu_entries = [e for e in _REGULATORY_CALENDAR if "EU AI Act" in e["framework"]]
        self.assertGreater(len(eu_entries), 0)

    def test_full_application_2027(self):
        full = [e for e in _REGULATORY_CALENDAR if "Full application" in e["event"]]
        self.assertEqual(len(full), 1)
        self.assertEqual(full[0]["date"], "2027-08-02")


# ── ComplianceChecker ────────────────────────────────────

class TestComplianceChecker(unittest.TestCase):
    def setUp(self):
        self.checker = ComplianceChecker()

    def test_check_returns_report(self):
        report = self.checker.check_aelu_compliance()
        self.assertIsInstance(report, ComplianceReport)
        self.assertEqual(len(report.surfaces), 10)

    def test_childrens_data_gap(self):
        report = self.checker.check_aelu_compliance()
        children = next(a for a in report.surfaces if a.surface.area == "childrens_data")
        self.assertEqual(children.status, "gap")
        self.assertTrue(any("COPPA" in g for g in children.gaps))

    def test_cross_border_gap(self):
        report = self.checker.check_aelu_compliance()
        cross = next(a for a in report.surfaces if a.surface.area == "cross_border_transfer")
        self.assertEqual(cross.status, "gap")

    def test_audio_recommendations(self):
        report = self.checker.check_aelu_compliance()
        audio = next(a for a in report.surfaces if a.surface.area == "audio_recordings")
        self.assertGreater(len(audio.recommendations), 0)

    def test_automated_decisions_compliant(self):
        report = self.checker.check_aelu_compliance()
        auto = next(a for a in report.surfaces if a.surface.area == "automated_decisions")
        self.assertEqual(auto.status, "compliant")

    def test_overall_status_not_compliant(self):
        report = self.checker.check_aelu_compliance()
        self.assertIn(report.overall_status, ("attention_needed", "action_required"))

    def test_action_items_generated(self):
        report = self.checker.check_aelu_compliance()
        self.assertGreater(len(report.action_items), 0)

    def test_institutional_recommendation(self):
        report = self.checker.check_aelu_compliance()
        inst = next(a for a in report.surfaces if a.surface.area == "institutional_data")
        self.assertTrue(any("FERPA" in r for r in inst.recommendations))

    def test_payment_processing_compliant(self):
        report = self.checker.check_aelu_compliance()
        pay = next(a for a in report.surfaces if a.surface.area == "payment_processing")
        self.assertEqual(pay.status, "compliant")


# ── ImpactAssessor ────────────────────────────────────────

class TestImpactAssessor(unittest.TestCase):
    def setUp(self):
        self.assessor = ImpactAssessor()

    def test_biometric_change(self):
        ia = self.assessor.assess_regulatory_change(
            "New biometric data regulations for voice analysis",
            RegulatoryFramework.STATE_AI_LAWS,
        )
        self.assertTrue(ia.affects_aelu)
        self.assertIn("audio_recordings", ia.affected_surfaces)
        self.assertGreater(ia.confidence, 0.5)

    def test_profiling_change(self):
        ia = self.assessor.assess_regulatory_change(
            "Updated requirements for automated profiling systems",
            RegulatoryFramework.GDPR,
        )
        self.assertTrue(ia.affects_aelu)
        self.assertTrue(
            "learning_analytics" in ia.affected_surfaces
            or "automated_decisions" in ia.affected_surfaces
        )

    def test_children_change(self):
        ia = self.assessor.assess_regulatory_change(
            "Stronger protections for children's online data",
            RegulatoryFramework.COPPA,
        )
        self.assertIn("childrens_data", ia.affected_surfaces)

    def test_payment_change(self):
        ia = self.assessor.assess_regulatory_change(
            "New payment processing requirements",
            RegulatoryFramework.GDPR,
        )
        self.assertIn("payment_processing", ia.affected_surfaces)

    def test_generic_change_falls_back_to_framework(self):
        ia = self.assessor.assess_regulatory_change(
            "General regulatory update with no specific keywords",
            RegulatoryFramework.FERPA,
        )
        self.assertTrue(ia.affects_aelu)
        self.assertGreater(len(ia.affected_surfaces), 0)

    def test_high_risk_change(self):
        ia = self.assessor.assess_regulatory_change(
            "New high-risk AI classification rules",
            RegulatoryFramework.EU_AI_ACT,
        )
        self.assertIn("learning_analytics", ia.affected_surfaces)
        self.assertTrue(any("Annex III" in c for c in ia.required_changes))

    def test_deletion_change(self):
        ia = self.assessor.assess_regulatory_change(
            "New right of deletion requirements",
            RegulatoryFramework.GDPR,
        )
        self.assertTrue(any("deletion" in c.lower() for c in ia.required_changes))

    def test_impact_level_high_for_audio(self):
        ia = self.assessor.assess_regulatory_change(
            "Audio biometric data must be processed differently",
            RegulatoryFramework.STATE_AI_LAWS,
        )
        self.assertEqual(ia.impact_level, "high")

    def test_timeline_medium_high_review(self):
        ia = self.assessor.assess_regulatory_change(
            "New biometric audio rules",
            RegulatoryFramework.STATE_AI_LAWS,
        )
        self.assertIn("Review within 30 days", ia.timeline)

    def test_marketing_keyword(self):
        ia = self.assessor.assess_regulatory_change(
            "New marketing consent requirements",
            RegulatoryFramework.GDPR,
        )
        self.assertIn("marketing_emails", ia.affected_surfaces)

    def test_transparency_keyword(self):
        ia = self.assessor.assess_regulatory_change(
            "Transparency requirements for generated content",
            RegulatoryFramework.EU_AI_ACT,
        )
        self.assertTrue(
            "ai_generated_content" in ia.affected_surfaces
            or "automated_decisions" in ia.affected_surfaces
        )

    def test_student_keyword(self):
        ia = self.assessor.assess_regulatory_change(
            "Updated student data protections",
            RegulatoryFramework.FERPA,
        )
        self.assertIn("institutional_data", ia.affected_surfaces)

    def test_cross_border_keyword(self):
        ia = self.assessor.assess_regulatory_change(
            "New cross-border data transfer mechanism",
            RegulatoryFramework.GDPR,
        )
        self.assertIn("cross_border_transfer", ia.affected_surfaces)


# ── ComplianceMonitor (main interface) ────────────────────

class TestComplianceMonitor(unittest.TestCase):
    def setUp(self):
        self.cm = ComplianceMonitor()

    def test_audit(self):
        report = self.cm.audit()
        self.assertIsInstance(report, ComplianceReport)
        self.assertEqual(len(report.surfaces), 10)

    def test_assess_change_by_value(self):
        ia = self.cm.assess_change("biometric data rules", "gdpr")
        self.assertTrue(ia.affects_aelu)

    def test_assess_change_by_name(self):
        ia = self.cm.assess_change("new rules", "eu_ai_act")
        self.assertTrue(ia.affects_aelu)

    def test_assess_change_invalid_framework(self):
        ia = self.cm.assess_change("something", "invalid_framework")
        self.assertIsInstance(ia, ImpactAssessment)

    def test_get_action_items_all(self):
        items = self.cm.get_action_items("all")
        self.assertGreater(len(items), 0)

    def test_get_action_items_filtered(self):
        all_items = self.cm.get_action_items("all")
        if any(i.urgency == "high" for i in all_items):
            high = self.cm.get_action_items("high")
            self.assertGreater(len(high), 0)
            for item in high:
                self.assertEqual(item.urgency, "high")

    def test_get_action_items_medium(self):
        medium = self.cm.get_action_items("medium")
        for item in medium:
            self.assertEqual(item.urgency, "medium")

    def test_regulatory_calendar(self):
        cal = self.cm.get_regulatory_calendar()
        self.assertGreater(len(cal), 5)

    def test_format_report(self):
        report = self.cm.audit()
        text = self.cm.format_report(report)
        self.assertIn("Compliance Report", text)
        self.assertIn("Overall:", text)
        self.assertIn("learner_data_collection", text)

    def test_format_report_gaps_shown(self):
        report = self.cm.audit()
        text = self.cm.format_report(report)
        self.assertIn("Gap:", text)

    def test_weekly_brief(self):
        brief = self.cm.weekly_brief()
        self.assertIn("Regulatory Brief", brief)
        self.assertIn("Compliance posture", brief)

    def test_weekly_brief_has_deadlines(self):
        brief = self.cm.weekly_brief()
        self.assertIn("Upcoming deadlines", brief)

    def test_weekly_brief_has_action_items(self):
        brief = self.cm.weekly_brief()
        self.assertIn("Action items", brief)


if __name__ == "__main__":
    unittest.main()
