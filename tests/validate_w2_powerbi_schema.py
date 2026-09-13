"""Validate the checked-in W2 PBIP/PBIR files against Microsoft schemas."""
import json
from pathlib import Path
from jsonschema import Draft7Validator

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "pbir_schemas"
BASE = ROOT / "dashboard" / "powerbi"
REPORT = BASE / "W2_Churn.Report"
MODEL = BASE / "W2_Churn.SemanticModel"


def validate(schema_name: str, path: Path):
    schema = json.loads((CACHE / schema_name).read_text(encoding="utf-8"))
    value = json.loads(path.read_text(encoding="utf-8"))
    return [error.message for error in Draft7Validator(schema).iter_errors(value)]


def main():
    checks = [
        ("pbip", "pbip_1.0.0.json", BASE / "W2_Churn.pbip"),
        ("report_definition", "report_definitionProperties_2.0.0.json", REPORT / "definition.pbir"),
        ("report_root", "report_report_2.0.0.json", REPORT / "definition" / "report.json"),
        ("report_version", "report_versionMetadata_1.0.0.json", REPORT / "definition" / "version.json"),
        ("report_pages", "report_pagesMetadata_1.0.0.json", REPORT / "definition" / "pages" / "pages.json"),
        ("semantic_definition", "semantic_definitionProperties_1.0.0.json", MODEL / "definition.pbism"),
    ]
    checks += [("page", "report_page_2.0.0.json", path) for path in sorted((REPORT / "definition" / "pages").glob("*/page.json"))]
    checks += [("visual", "report_visualContainer_2.9.0.json", path) for path in sorted((REPORT / "definition" / "pages").glob("*/visuals/*/visual.json"))]
    results = []
    for kind, schema_name, path in checks:
        try:
            errors = validate(schema_name, path)
        except Exception as exc:  # pragma: no cover - diagnostic path
            errors = [repr(exc)]
        results.append({"kind": kind, "path": path.relative_to(ROOT).as_posix(), "schema": schema_name,
                        "status": "passed" if not errors else "failed", "errors": errors})
    failures = [result for result in results if result["status"] == "failed"]
    report = {"project": "W2_Churn", "validator": "jsonschema Draft7Validator",
              "total_files": len(results), "passed_files": len(results) - len(failures),
              "failed_files": len(failures), "status": "passed" if not failures else "failed",
              "checks": results}
    out = ROOT / "reports" / "w2_powerbi_verification.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "total_files", "passed_files", "failed_files")}))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
