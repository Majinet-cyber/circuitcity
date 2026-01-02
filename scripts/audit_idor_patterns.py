#!/usr/bin/env python
"""
IDOR Security Audit Script
===========================

Scans Django views for potential Insecure Direct Object Reference vulnerabilities.

Usage:
    python scripts/audit_idor_patterns.py

This script identifies view functions/classes that:
1. Use get_object_or_404() without business filtering
2. Accept object IDs from URLs (e.g., pk, id parameters)
3. Don't use @require_business or similar decorators
4. Query models without .filter(business=...)

False positives are expected - manual review is required.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass, field


@dataclass
class ViewAuditResult:
    """Result of auditing a single view function/class."""

    file_path: str
    view_name: str
    line_number: int
    risk_level: str  # "HIGH", "MEDIUM", "LOW"
    issues: List[str] = field(default_factory=list)
    has_business_filter: bool = False
    has_require_business: bool = False
    uses_get_object_or_404: bool = False
    accepts_pk_parameter: bool = False


class IDORAuditor:
    """Audit Django views for IDOR vulnerabilities."""

    # Models that should always be scoped to business
    TENANT_SCOPED_MODELS = {
        "Business",
        "Membership",
        "Location",
        "InventoryItem",
        "Product",
        "Sale",
        "Doc",
        "DocLine",
        "WalletTransaction",
        "BackupSnapshot",
        "GymMember",
        "LiquorProduct",
        "LiquorShift",
        "PharmacyBatch",
        "ClothingSale",
        "GroceryStockItem",
        "AgentInvite",
        "TimeLog",
        "LaybyOrder",
        "Notification",
    }

    # Decorators that indicate business protection
    PROTECTION_DECORATORS = {
        "@require_business",
        "@manager_required",
        "@require_role",
        "@require_business_kind",
        "@otp_required",
    }

    # Safe patterns (views that are likely secure)
    SAFE_PATTERNS = [
        r"filter\(business=",
        r"filter\(.*business=",
        r"\.business\s*=\s*business",
        r"scope_qs_to_user",
        r"scope_queryset_to_business",
        r"get_active_business",
    ]

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results: List[ViewAuditResult] = []

    def audit_file(self, file_path: Path) -> List[ViewAuditResult]:
        """Audit a single Python file for IDOR vulnerabilities."""
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"⚠️  Could not read {file_path}: {e}")
            return []

        results = []

        # Find all view functions/classes
        try:
            tree = ast.parse(content, filename=str(file_path))
        except SyntaxError:
            print(f"⚠️  Syntax error in {file_path}")
            return []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result = self._audit_function(node, content, file_path)
                if result:
                    results.append(result)
            elif isinstance(node, ast.ClassDef):
                # Check if it's a view class (inherits from View, TemplateView, etc.)
                if self._is_view_class(node):
                    result = self._audit_class(node, content, file_path)
                    if result:
                        results.append(result)

        return results

    def _is_view_class(self, node: ast.ClassDef) -> bool:
        """Check if a class is likely a Django view."""
        if not node.bases:
            return False

        view_base_names = {
            "View",
            "TemplateView",
            "ListView",
            "DetailView",
            "CreateView",
            "UpdateView",
            "DeleteView",
            "FormView",
            "LoginRequiredMixin",
            "APIView",
        }

        for base in node.bases:
            if isinstance(base, ast.Name) and base.id in view_base_names:
                return True
            if isinstance(base, ast.Attribute) and base.attr in view_base_names:
                return True

        return False

    def _audit_function(self, node: ast.FunctionDef, content: str, file_path: Path) -> ViewAuditResult | None:
        """Audit a function for IDOR vulnerabilities."""
        # Skip non-view functions (crude heuristic: must accept 'request' parameter)
        if not any(arg.arg == "request" for arg in node.args.args):
            return None

        # Skip test functions
        if node.name.startswith("test_"):
            return None

        # Extract function source
        try:
            lines = content.splitlines()
            func_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
        except Exception:
            func_source = ""

        result = ViewAuditResult(
            file_path=str(file_path.relative_to(self.project_root)),
            view_name=node.name,
            line_number=node.lineno,
            risk_level="LOW",
        )

        # Check for decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        result.has_require_business = any(d in self.PROTECTION_DECORATORS for d in decorators)

        # Check for business filtering patterns
        result.has_business_filter = any(re.search(pattern, func_source) for pattern in self.SAFE_PATTERNS)

        # Check for get_object_or_404 usage
        result.uses_get_object_or_404 = "get_object_or_404" in func_source

        # Check for ID/PK parameters in function signature
        param_names = [arg.arg for arg in node.args.args]
        result.accepts_pk_parameter = any(
            name in param_names for name in ["pk", "id", "item_id", "sale_id", "doc_id", "snapshot_id", "product_id"]
        )

        # Assess risk
        issues = []

        if result.accepts_pk_parameter and result.uses_get_object_or_404:
            if not result.has_business_filter and not result.has_require_business:
                result.risk_level = "HIGH"
                issues.append("⚠️  Accepts ID parameter + uses get_object_or_404 WITHOUT business filter")
            elif not result.has_business_filter:
                result.risk_level = "MEDIUM"
                issues.append("🔍 Has @require_business but get_object_or_404 may lack .filter(business=)")

        elif result.accepts_pk_parameter and not result.has_business_filter:
            result.risk_level = "MEDIUM"
            issues.append("🔍 Accepts ID parameter but no obvious business filter")

        elif result.uses_get_object_or_404 and not result.has_business_filter:
            result.risk_level = "LOW"
            issues.append("ℹ️  Uses get_object_or_404 but no obvious business filter (may be safe)")

        result.issues = issues

        # Only return results with potential issues
        return result if result.risk_level in ["HIGH", "MEDIUM"] else None

    def _audit_class(self, node: ast.ClassDef, content: str, file_path: Path) -> ViewAuditResult | None:
        """Audit a view class for IDOR vulnerabilities."""
        # Extract class source
        try:
            lines = content.splitlines()
            class_source = "\n".join(lines[node.lineno - 1 : node.end_lineno])
        except Exception:
            class_source = ""

        result = ViewAuditResult(
            file_path=str(file_path.relative_to(self.project_root)),
            view_name=node.name,
            line_number=node.lineno,
            risk_level="LOW",
        )

        # Check for business filtering patterns
        result.has_business_filter = any(re.search(pattern, class_source) for pattern in self.SAFE_PATTERNS)

        # Check for get_object_or_404 usage
        result.uses_get_object_or_404 = "get_object_or_404" in class_source

        # Check if it's a detail view (likely accepts PK)
        if any(
            base_name in ["DetailView", "UpdateView", "DeleteView"]
            for base in node.bases
            for base_name in [getattr(base, "id", ""), getattr(base, "attr", "")]
        ):
            result.accepts_pk_parameter = True

        # Assess risk
        issues = []

        if result.accepts_pk_parameter and not result.has_business_filter:
            result.risk_level = "HIGH"
            issues.append("⚠️  DetailView/UpdateView/DeleteView WITHOUT business filtering")

        elif result.uses_get_object_or_404 and not result.has_business_filter:
            result.risk_level = "MEDIUM"
            issues.append("🔍 Uses get_object_or_404 but no obvious business filter")

        result.issues = issues

        # Only return results with potential issues
        return result if result.risk_level in ["HIGH", "MEDIUM"] else None

    def _get_decorator_name(self, node: ast.expr) -> str:
        """Extract decorator name from AST node."""
        if isinstance(node, ast.Name):
            return f"@{node.id}"
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return f"@{node.func.id}"
        elif isinstance(node, ast.Attribute):
            return f"@{node.attr}"
        return ""

    def audit_directory(self, directory: Path, pattern: str = "views*.py") -> List[ViewAuditResult]:
        """Audit all view files in a directory."""
        results = []

        for file_path in directory.rglob(pattern):
            if file_path.is_file() and not file_path.name.startswith("test_"):
                file_results = self.audit_file(file_path)
                results.extend(file_results)

        return results

    def generate_report(self, results: List[ViewAuditResult]) -> str:
        """Generate a human-readable audit report."""
        high_risk = [r for r in results if r.risk_level == "HIGH"]
        medium_risk = [r for r in results if r.risk_level == "MEDIUM"]

        report = []
        report.append("=" * 80)
        report.append("IDOR SECURITY AUDIT REPORT")
        report.append("=" * 80)
        report.append("")
        report.append(f"Total issues found: {len(results)}")
        report.append(f"  - HIGH risk: {len(high_risk)}")
        report.append(f"  - MEDIUM risk: {len(medium_risk)}")
        report.append("")

        if high_risk:
            report.append("=" * 80)
            report.append("HIGH RISK (Immediate Review Required)")
            report.append("=" * 80)
            report.append("")

            for r in high_risk:
                report.append(f"📍 {r.file_path}:{r.line_number}")
                report.append(f"   View: {r.view_name}")
                for issue in r.issues:
                    report.append(f"   {issue}")
                report.append("")

        if medium_risk:
            report.append("=" * 80)
            report.append("MEDIUM RISK (Review Recommended)")
            report.append("=" * 80)
            report.append("")

            for r in medium_risk:
                report.append(f"📍 {r.file_path}:{r.line_number}")
                report.append(f"   View: {r.view_name}")
                for issue in r.issues:
                    report.append(f"   {issue}")
                report.append("")

        report.append("=" * 80)
        report.append("RECOMMENDATIONS")
        report.append("=" * 80)
        report.append("")
        report.append("For HIGH risk items:")
        report.append("  1. Add .filter(business=business) to get_object_or_404() calls")
        report.append("  2. Verify @require_business decorator is present")
        report.append("  3. Test cross-tenant access manually")
        report.append("")
        report.append("For MEDIUM risk items:")
        report.append("  1. Review code to confirm business filtering is present")
        report.append("  2. Add explicit .filter(business=...) if missing")
        report.append("  3. Add test cases to security test suite")
        report.append("")
        report.append("=" * 80)

        return "\n".join(report)


def main():
    """Run IDOR audit on the project."""
    import sys

    # Determine project root
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent  # Assumes scripts/ is in project root

    print(f"🔍 Auditing project at: {project_root}")
    print("")

    auditor = IDORAuditor(project_root)

    # Audit key directories
    apps_to_audit = [
        "inventory",
        "sales",
        "wallet",
        "backups",
        "layby",
        "billing",
        "notifications",
        "support",
        "audit",
        "hq",
        "circuitcity/accounts",
    ]

    all_results = []

    for app in apps_to_audit:
        app_path = project_root / app
        if app_path.exists():
            print(f"Scanning {app}...")
            results = auditor.audit_directory(app_path)
            all_results.extend(results)

    print("")
    print(f"✅ Audit complete. Found {len(all_results)} potential issues.")
    print("")

    # Generate report
    report = auditor.generate_report(all_results)
    print(report)

    # Save report to file
    report_path = project_root / "docs" / "IDOR_AUDIT_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n📄 Full report saved to: {report_path}")

    # Exit with error code if HIGH risk issues found
    high_risk_count = len([r for r in all_results if r.risk_level == "HIGH"])
    if high_risk_count > 0:
        print(f"\n❌ {high_risk_count} HIGH risk issues require immediate attention!")
        sys.exit(1)
    else:
        print("\n✅ No HIGH risk issues found. Manual review of MEDIUM risk items recommended.")
        sys.exit(0)


if __name__ == "__main__":
    main()
