from __future__ import annotations

from sqlalchemy import or_

from ..extensions import db
from ..models.agreement import (
    AgmtCommitment,
    AgmtHeaderStg,
    AgmtMdlNormalStg,
    AgmtModelsStg,
)


def _normalize_partner_name(partner_name: str) -> str:
    return " ".join(partner_name.strip().lower().split())


def _agreement_table(title: str, headers: list[str], rows: list[list[str]]) -> dict:
    return {"title": title, "headers": headers, "rows": rows}


def get_baseline_rates(partner_name: str) -> dict:
    """Return baseline agreement data for the given partner name.

    The returned structure matches the extractor output shape so it can be fed
    directly into the orchestrator comparison path.
    """

    if not partner_name or not partner_name.strip():
        return {"partner_name": partner_name, "tables": []}

    normalized_partner = _normalize_partner_name(partner_name)

    headers = (
        AgmtHeaderStg.query.filter(
            or_(
                db.func.lower(db.func.trim(AgmtHeaderStg.sender)) == normalized_partner,
                db.func.lower(db.func.trim(AgmtHeaderStg.rp)) == normalized_partner,
            )
        )
        .order_by(AgmtHeaderStg.created_date.desc().nullslast(), AgmtHeaderStg.agmt_id)
        .all()
    )

    if not headers:
        like_partner = f"%{partner_name.strip()}%"
        headers = (
            AgmtHeaderStg.query.filter(
                or_(
                    AgmtHeaderStg.sender.ilike(like_partner),
                    AgmtHeaderStg.rp.ilike(like_partner),
                )
            )
            .order_by(
                AgmtHeaderStg.created_date.desc().nullslast(), AgmtHeaderStg.agmt_id
            )
            .all()
        )

    if not headers:
        return {"partner_name": partner_name, "tables": []}

    agmt_ids = [header.agmt_id for header in headers if header.agmt_id]
    tables: list[dict] = []

    model_rows = (
        db.session.query(AgmtModelsStg, AgmtMdlNormalStg)
        .join(
            AgmtMdlNormalStg,
            (AgmtModelsStg.agmt_id == AgmtMdlNormalStg.agmt_id)
            & (AgmtModelsStg.model_seq == AgmtMdlNormalStg.model_seq),
            isouter=True,
        )
        .filter(AgmtModelsStg.agmt_id.in_(agmt_ids))
        .order_by(AgmtModelsStg.agmt_id, AgmtModelsStg.model_seq)
        .all()
    )

    commitments = (
        AgmtCommitment.query.filter(AgmtCommitment.agmt_id.in_(agmt_ids))
        .order_by(AgmtCommitment.agmt_id, AgmtCommitment.commitment_name)
        .all()
    )

    rows_by_agmt: dict[str, list[list[str]]] = {}
    for model, normal in model_rows:
        model_name = model.model_name or model.model_type or f"MODEL_{model.model_seq}"
        charge_value = (
            normal.charge_field if normal and normal.charge_field is not None else ""
        )
        rows_by_agmt.setdefault(model.agmt_id, []).append(
            [
                model_name,
                charge_value,
                model.model_type or "",
                model.agmt_id,
                model.model_seq,
            ]
        )

    commitment_rows_by_agmt: dict[str, list[list[str]]] = {}
    for commitment in commitments:
        commitment_rows_by_agmt.setdefault(commitment.agmt_id, []).append(
            [
                commitment.commitment_name or "",
                commitment.amount or "",
                commitment.commitment_type or "",
                commitment.direction or "",
                commitment.agmt_id,
            ]
        )

    for header in headers:
        if header.agmt_id in rows_by_agmt:
            tables.append(
                _agreement_table(
                    f"AGMT_MDL_NORMAL_STG - {header.agmt_id}",
                    [
                        "MODEL_NAME",
                        "CHARGE_FIELD",
                        "MODEL_TYPE",
                        "AGMT_ID",
                        "MODEL_SEQ",
                    ],
                    rows_by_agmt[header.agmt_id],
                )
            )

        if header.agmt_id in commitment_rows_by_agmt:
            tables.append(
                _agreement_table(
                    f"AGMT_COMMITMENT - {header.agmt_id}",
                    [
                        "COMMITMENT_NAME",
                        "AMOUNT",
                        "COMMITMENT_TYPE",
                        "DIRECTION",
                        "AGMT_ID",
                    ],
                    commitment_rows_by_agmt[header.agmt_id],
                )
            )

    return {"partner_name": partner_name, "tables": tables}
