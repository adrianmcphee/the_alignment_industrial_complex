#!/usr/bin/env python3
"""Validate the Technical Field Guide v0.3 package and its broken fixtures."""

from __future__ import annotations

import argparse
import hashlib
import re
from collections import deque
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parent
AS_OF = date(2026, 8, 26)
SEMVER = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
ERROR_IDS = [f"V{number:03d}" for number in range(1, 26)]
WARN_IDS = [f"W{number:03d}" for number in range(1, 5)]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"{path} does not contain a YAML object")
    return value


def artifact_paths(include_broken: bool = False) -> list[Path]:
    roots = [ROOT / "protocols", ROOT / "rules", ROOT / "instances" / "minimum", ROOT / "instances" / "complete", ROOT / "instances" / "evidence"]
    if include_broken:
        roots.append(ROOT / "instances" / "broken")
    return sorted(path for root in roots for path in root.glob("*.yaml"))


def scalar_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for nested in value.values() for item in scalar_values(nested)]
    if isinstance(value, list):
        return [item for nested in value for item in scalar_values(nested)]
    return [str(value)]


def transitions_to(transition: dict[str, Any]) -> list[str]:
    target = transition.get("to", [])
    return target if isinstance(target, list) else [target]


def get_path(instance: dict[str, Any], dotted: str) -> Any:
    value: Any = instance
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def non_empty(value: Any) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def iso_date(value: str) -> date:
    return date.fromisoformat(value[:10])


def canonical_archive_digest(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(ROOT).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def validate_package() -> dict[str, Any]:
    schema_paths = sorted((ROOT / "schemas").glob("*.yaml"))
    schemas = [load_yaml(path) for path in schema_paths]
    schema_by_id = {schema["$id"]: schema for schema in schemas}
    for schema in schemas:
        Draft202012Validator.check_schema(schema)

    paths = artifact_paths()
    artifacts = [load_yaml(path) | {"_path": str(path.relative_to(ROOT))} for path in paths]
    schema_failures: list[str] = []
    for artifact in artifacts:
        schema_key = f'{artifact.get("schema_id")}:{artifact.get("schema_version")}'
        schema = schema_by_id.get(schema_key)
        if schema is None:
            schema_failures.append(f'{artifact["_path"]}: unresolved schema {schema_key}')
            continue
        candidate = {key: value for key, value in artifact.items() if key != "_path"}
        errors = sorted(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(candidate), key=lambda error: list(error.path))
        schema_failures.extend(f'{artifact["_path"]}: {error.message}' for error in errors)

    by_type: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        by_type.setdefault(artifact["artifact_type"], []).append(artifact)
    processes = by_type.get("process_definition", [])
    evaluations = by_type.get("model_evaluation_record", [])
    contracts = by_type.get("published_contract", [])
    charters = by_type.get("unit_charter", [])
    reports = by_type.get("drift_report", [])
    evaluation_by_id = {item["id"]: item for item in evaluations}
    process_by_id = {item["id"]: item for item in processes}
    contract_by_id = {item["id"]: item for item in contracts}

    failures: dict[str, list[str]] = {rule_id: [] for rule_id in ERROR_IDS + WARN_IDS}
    not_applicable: dict[str, str] = {}

    for artifact in artifacts:
        schema_key = f'{artifact.get("schema_id")}:{artifact.get("schema_version")}'
        if schema_key not in schema_by_id:
            failures["V001"].append(f'{artifact["_path"]}: schema does not resolve')
        if not SEMVER.fullmatch(str(artifact.get("version", ""))) or not SEMVER.fullmatch(str(artifact.get("schema_version", ""))):
            failures["V002"].append(f'{artifact["_path"]}: version is not semantic')

    for process in processes:
        states = set(process["states"])
        transitions = process["transitions"]
        for transition in transitions:
            if transition["from"] not in states:
                failures["V003"].append(f'{process["id"]}.{transition["id"]}: unknown from state {transition["from"]}')
            for target in transitions_to(transition):
                if target not in states:
                    failures["V004"].append(f'{process["id"]}.{transition["id"]}: unknown to state {target}')
        identifiers = list(states) + [item["id"] for item in process["invariants"]] + [item["id"] for item in transitions]
        if len(identifiers) != len(set(identifiers)):
            failures["V005"].append(f'{process["id"]}: duplicate state, invariant, or transition id')
        terminals = set(process["terminal_outcomes"])
        for terminal in terminals - states:
            failures["V006"].append(f'{process["id"]}: terminal {terminal} is not a state')
        graph: dict[str, set[str]] = {state: set() for state in states}
        for transition in transitions:
            if transition["from"] in graph:
                graph[transition["from"]].update(target for target in transitions_to(transition) if target in states)
        reached = {process["entry_state"]}
        queue = deque(reached)
        while queue:
            state = queue.popleft()
            for target in graph.get(state, set()) - reached:
                reached.add(target)
                queue.append(target)
        for terminal in terminals - reached:
            failures["V007"].append(f'{process["id"]}: terminal {terminal} is unreachable')
        for terminal in terminals:
            if graph.get(terminal):
                failures["V008"].append(f'{process["id"]}: terminal {terminal} has an outgoing transition')
        if not terminals or process.get("terminal_outcome_cardinality") not in {"exactly_one", "one_or_more"}:
            failures["V008"].append(f'{process["id"]}: terminal cardinality is not satisfiable')
        for transition in transitions:
            if not non_empty(transition.get("event")):
                failures["V009"].append(f'{process["id"]}.{transition["id"]}: event is missing')
        for invariant in process["invariants"]:
            if not non_empty(invariant.get("rule")) and len(invariant) <= 2:
                failures["V009"].append(f'{process["id"]}.{invariant["id"]}: invariant is not inspectable')
        process_text = " ".join(scalar_values(process))
        for required_identity in ("process_cycle_id", "decision_record_id", "process_definition_version", "deployment_digest"):
            if required_identity not in process_text:
                failures["V010"].append(f'{process["id"]}: {required_identity} is not required')

        for invariant in process["invariants"]:
            evaluation_id = invariant.get("evaluation_id")
            if not evaluation_id:
                continue
            evaluation = evaluation_by_id.get(evaluation_id)
            if evaluation is None:
                failures["V011"].append(f'{process["id"]}: evaluation {evaluation_id} does not resolve')
                continue
            if str(evaluation["process_definition_version"]) != str(process["version"]):
                failures["V011"].append(f'{process["id"]}: evaluation references process version {evaluation["process_definition_version"]}')
            process_stops = set(invariant.get("forced_referral_conditions", []))
            evaluation_stops = set(evaluation["authority"]["forced_referral_conditions"])
            for missing in evaluation_stops - process_stops:
                failures["V012"].append(f'{process["id"]}: missing forced referral condition {missing}')
            if invariant.get("referral_threshold") != evaluation["test"].get("threshold"):
                failures["V021"].append(f'{process["id"]}: threshold {invariant.get("referral_threshold")} differs from approved {evaluation["test"].get("threshold")}')
            if invariant.get("threshold_comparison") != evaluation["test"].get("threshold_comparison"):
                failures["V021"].append(f'{process["id"]}: comparison direction differs from the evaluation')

        for contract_id in process.get("published_contracts", []):
            contract = contract_by_id.get(contract_id)
            if contract is None:
                failures["V024"].append(f'{process["id"]}: contract {contract_id} does not resolve')
            elif process.get("reason_code_registry") and contract.get("reason_code_registry") != process.get("reason_code_registry"):
                failures["V017"].append(f'{process["id"]}: reason-code registry differs from {contract_id}')
        published = set(process.get("published_contracts", []))
        for transition in transitions:
            event_id = transition.get("publishes_event")
            contract_id = transition.get("published_contract")
            if bool(event_id) != bool(contract_id):
                failures["V024"].append(f'{process["id"]}.{transition["id"]}: publication event and contract must be structured together')
            if contract_id and contract_id not in published:
                failures["V024"].append(f'{process["id"]}.{transition["id"]}: contract {contract_id} is not declared')
            contract = contract_by_id.get(contract_id) if contract_id else None
            if event_id and contract and event_id not in contract["published_events"]:
                failures["V024"].append(f'{process["id"]}.{transition["id"]}: event {event_id} is absent from {contract_id}')

    for evaluation in evaluations:
        if iso_date(evaluation["expiry"]["date"]) <= iso_date(evaluation["generated_at"]):
            failures["V013"].append(f'{evaluation["id"]}: expiry does not postdate generation')
        provenance = evaluation.get("provenance", {})
        for key in ("dataset", "protocol", "features", "model_digest", "validation_id"):
            if not non_empty(provenance.get(key)):
                failures["V014"].append(f'{evaluation["id"]}: provenance {key} is missing')
        if (iso_date(evaluation["expiry"]["date"]) - AS_OF).days <= 30:
            failures["W001"].append(f'{evaluation["id"]}: expiry is not more than 30 days ahead')

    for contract in contracts:
        meanings = list(contract["published_events"].values())
        if len(meanings) != len(set(meanings)):
            failures["V015"].append(f'{contract["id"]}: event meanings are not unique')
        required = {"event_id", "occurred_at", "process_cycle_id", "process_definition_version", "decision_record_id"}
        missing = required - set(contract["required_envelope"])
        if missing:
            failures["V016"].append(f'{contract["id"]}: missing envelope fields {sorted(missing)}')
        if not contract.get("superseded_major_versions"):
            not_applicable["W004"] = "No superseded major version is declared in the worked contracts."

    reserved_fields = {"holder", "trigger", "evidence", "decision_clock", "escalation", "return_transition"}
    for charter in charters:
        for index, right in enumerate(charter["reserved_independent_rights"], start=1):
            missing = reserved_fields - set(right)
            if missing:
                failures["V018"].append(f'{charter["id"]}.reserved_right[{index}]: missing {sorted(missing)}')
        process = process_by_id.get(charter["process"])
        if process is None:
            failures["V025"].append(f'{charter["id"]}: process {charter["process"]} does not resolve')
        elif process["owners"].get("process") != charter["accountability"]["ordinary_process"].get("holder"):
            failures["V025"].append(f'{charter["id"]}: ordinary accountability holder differs from the process owner')

    join_keys = {"process_cycle_id", "decision_record_id", "deployment_digest", "model_digest", "evaluation_id"}
    for report in reports:
        for finding in report["findings"]:
            observed = set(finding.get("provenance", {}).get("join_keys", []))
            if not join_keys <= observed:
                failures["V019"].append(f'{report["id"]}.{finding["id"]}: missing join keys {sorted(join_keys - observed)}')
            if finding.get("severity") in {"medium", "high", "critical"}:
                disposition = finding.get("human_disposition", {})
                has_date = non_empty(disposition.get("due_date")) or non_empty(disposition.get("review_due"))
                has_closure = non_empty(disposition.get("closure_requires")) or non_empty(disposition.get("re_exposure_requires"))
                if not non_empty(disposition.get("owner")) or not has_date or not has_closure:
                    failures["V020"].append(f'{report["id"]}.{finding["id"]}: disposition is incomplete')
                due = disposition.get("due_date") or disposition.get("review_due")
                if due and iso_date(str(due)) < AS_OF and report.get("status") not in {"closed", "superseded"}:
                    failures["W003"].append(f'{report["id"]}.{finding["id"]}: recorded date {due} has passed')
        floor = report["coverage"].get("floor_percent")
        if floor is None:
            failures["W002"].append(f'{report["id"]}: coverage floor is not declared')
        elif report["coverage"].get("percent", 0) < floor:
            failures["W002"].append(f'{report["id"]}: coverage is below its declared floor')

    maturity_items = [artifact for artifact in artifacts if artifact.get("maturity")]
    for artifact in maturity_items:
        for field in artifact["maturity"].get("mandatory_now", []):
            if not non_empty(get_path(artifact, field)):
                failures["V022"].append(f'{artifact["id"]}: mandatory maturity field {field} is empty')
    if not any(artifact.get("prior_version") for artifact in maturity_items):
        not_applicable["V023"] = "The packet contains initial maturity declarations, not a maturity-stage change."

    rules = load_yaml(ROOT / "rules" / "end-of-alignment-core-validation-2.0.0.yaml")
    rule_by_id = {rule["id"]: rule for rule in rules["rules"]}
    expected_ids = set(ERROR_IDS + WARN_IDS)
    if set(rule_by_id) != expected_ids:
        schema_failures.append("rule set ids do not equal V001-V025 and W001-W004")

    rule_results: list[dict[str, Any]] = []
    for rule_id in ERROR_IDS + WARN_IDS:
        rule = rule_by_id[rule_id]
        problems = failures[rule_id]
        if problems:
            status = "error" if rule["severity"] == "error" else "warn"
        elif rule_id in not_applicable:
            status = "not_applicable"
        else:
            status = "pass"
        result: dict[str, Any] = {"id": rule_id, "severity": rule["severity"], "status": status}
        if problems:
            result["details"] = problems
        elif rule_id in not_applicable:
            result["details"] = [not_applicable[rule_id]]
        rule_results.append(result)

    broken_results = validate_broken(schema_by_id, evaluation_by_id)
    error_failures = [result for result in rule_results if result["status"] == "error"]
    schema_versions = {
        schema["properties"]["artifact_type"]["const"]: schema["$id"].rsplit(":", 1)[1]
        for schema in schemas
    }
    validation_archive_paths = [
        ROOT / "validate.py",
        ROOT / "requirements.txt",
        *schema_paths,
        *artifact_paths(include_broken=True),
    ]
    return {
        "guide_version": "0.3",
        "validated_at": AS_OF.isoformat(),
        "rule_set_version": rules["rule_set_version"],
        "validation_provenance": {
            "rule_set_id": rules["rule_set_id"],
            "rule_set_version": rules["rule_set_version"],
            "schema_versions": dict(sorted(schema_versions.items())),
            "validation_archive_digest": {
                "algorithm": "sha256",
                "format": "canonical-path-byte-stream-v1",
                "scope": "relative path and bytes of the validator, requirements, schemas, rules, protocols, governed artefacts, and broken fixtures; excludes generated results",
                "value": canonical_archive_digest(validation_archive_paths),
            },
        },
        "complete_packet": {
            "schema_contracts": len(schemas),
            "governed_artefacts": len(artifacts),
            "schema_errors": schema_failures,
            "rule_results": rule_results,
            "summary": {
                "error_failures": len(error_failures),
                "warnings": sum(result["status"] == "warn" for result in rule_results),
                "not_applicable": sum(result["status"] == "not_applicable" for result in rule_results),
            },
        },
        "broken_packet": broken_results,
    }


def validate_broken(schema_by_id: dict[str, dict[str, Any]], evaluation_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    fixtures = sorted((ROOT / "instances" / "broken").glob("*.yaml"))
    for path in fixtures:
        instance = load_yaml(path)
        schema = schema_by_id[f'{instance["schema_id"]}:{instance["schema_version"]}']
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(instance)
        detected: list[str] = []
        if path.name.startswith("01-"):
            states = set(instance["states"])
            if any(target not in states for transition in instance["transitions"] for target in transitions_to(transition)):
                detected.append("V004")
            expected = ["V004"]
        elif path.name.startswith("02-"):
            if iso_date(instance["expiry"]["date"]) <= iso_date(instance["generated_at"]):
                detected.append("V013")
            expected = ["V013"]
        elif path.name.startswith("03-"):
            invariant = next(item for item in instance["invariants"] if item.get("evaluation_id"))
            evaluation = evaluation_by_id[invariant["evaluation_id"]]
            if invariant.get("referral_threshold") != evaluation["test"].get("threshold") or invariant.get("threshold_comparison") != evaluation["test"].get("threshold_comparison"):
                detected.append("V021")
            expected = ["V021"]
        else:
            expected = []
            required = {"holder", "trigger", "evidence", "decision_clock", "escalation", "return_transition"}
            if any(not required <= set(right) for right in instance["reserved_independent_rights"]):
                detected.append("V018")
        result: dict[str, Any] = {
            "fixture": str(path.relative_to(ROOT)),
            "schema_status": "pass",
            "expected_rules": expected,
            "detected_rules": detected,
            "expectation_met": detected == expected,
        }
        if not expected:
            result["known_gap"] = "A reserved-right holder can equal the prohibited holder. V018 tests presence, not mutual exclusion against an institutional register."
        results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-results", action="store_true", help="write validation/validation-results.yaml")
    arguments = parser.parse_args()
    results = validate_package()
    if arguments.write_results:
        output = ROOT / "validation" / "validation-results.yaml"
        output.write_text(yaml.safe_dump(results, sort_keys=False, width=100), encoding="utf-8")
        print(output)
    summary = results["complete_packet"]["summary"]
    broken_ok = all(item["expectation_met"] for item in results["broken_packet"])
    schemas_ok = not results["complete_packet"]["schema_errors"]
    warning_word = "warning" if summary["warnings"] == 1 else "warnings"
    print(f'Field Guide v0.3: {summary["error_failures"]} error failures, {summary["warnings"]} {warning_word}, broken fixtures expected={broken_ok}')
    return 0 if summary["error_failures"] == 0 and broken_ok and schemas_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
