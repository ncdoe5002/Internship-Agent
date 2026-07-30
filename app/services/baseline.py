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


def _agreement_table(title: str, headers: list[str], rows: list[list]) -> dict:
    return {"title": title, "headers": headers, "rows": rows}


def get_baseline_rates(partner_name: str) -> dict:
    """Return baseline agreement data for the given partner name.

    The returned structure matches the extractor output shape so it can be fed
    directly into the orchestrator comparison path.
    """

    if not partner_name or not partner_name.strip():
        return {"partner_name": partner_name, "tables": []}

    normalized_partner = _normalize_partner_name(partner_name)

    # NOTE: ORM attribute names match the Python column names (uppercase) as defined
    # on the model class, e.g. AgmtHeaderStg.SENDER, .RP, .CREATED_DATE, .AGMT_ID.
    headers = (
        AgmtHeaderStg.query.filter(
            or_(
                db.func.lower(db.func.trim(AgmtHeaderStg.SENDER)) == normalized_partner,
                db.func.lower(db.func.trim(AgmtHeaderStg.RP)) == normalized_partner,
            )
        )
        .order_by(AgmtHeaderStg.CREATED_DATE.desc().nullslast(), AgmtHeaderStg.AGMT_ID)
        .all()
    )

    if not headers:
        like_partner = f"%{partner_name.strip()}%"
        headers = (
            AgmtHeaderStg.query.filter(
                or_(
                    AgmtHeaderStg.SENDER.ilike(like_partner),
                    AgmtHeaderStg.RP.ilike(like_partner),
                )
            )
            .order_by(
                AgmtHeaderStg.CREATED_DATE.desc().nullslast(), AgmtHeaderStg.AGMT_ID
            )
            .all()
        )

    if not headers:
        return {"partner_name": partner_name, "tables": []}

    agmt_ids = [header.AGMT_ID for header in headers if header.AGMT_ID]
    tables: list[dict] = []

    model_rows = (
        db.session.query(AgmtModelsStg, AgmtMdlNormalStg)
        .join(
            AgmtMdlNormalStg,
            (AgmtModelsStg.AGMT_ID == AgmtMdlNormalStg.AGMT_ID)
            & (AgmtModelsStg.MODEL_SEQ == AgmtMdlNormalStg.MODEL_SEQ),
            isouter=True,
        )
        .filter(AgmtModelsStg.AGMT_ID.in_(agmt_ids))
        .order_by(AgmtModelsStg.AGMT_ID, AgmtModelsStg.MODEL_SEQ)
        .all()
    )

    commitments = (
        AgmtCommitment.query.filter(AgmtCommitment.AGMT_ID.in_(agmt_ids))
        .order_by(AgmtCommitment.AGMT_ID, AgmtCommitment.COMMITMENT_NAME)
        .all()
    )

    rows_by_agmt: dict[str, list[list]] = {}
    for model, normal in model_rows:
        model_name = model.MODEL_NAME or model.MODEL_TYPE or f"MODEL_{model.MODEL_SEQ}"
        charge_value = (
            normal.CHARGE_FIELD if normal and normal.CHARGE_FIELD is not None else ""
        )
        rows_by_agmt.setdefault(model.AGMT_ID, []).append(
            [
                model_name,
                charge_value,
                model.MODEL_TYPE or "",
                model.AGMT_ID,
                model.MODEL_SEQ,
            ]
        )

    commitment_rows_by_agmt: dict[str, list[list]] = {}
    for commitment in commitments:
        commitment_rows_by_agmt.setdefault(commitment.AGMT_ID, []).append(
            [
                commitment.COMMITMENT_NAME or "",
                commitment.AMOUNT or "",
                commitment.COMMITMENT_TYPE or "",
                commitment.DIRECTION or "",
                commitment.AGMT_ID,
            ]
        )

    for header in headers:
        if header.AGMT_ID in rows_by_agmt:
            tables.append(
                _agreement_table(
                    f"AGMT_MDL_NORMAL_STG - {header.AGMT_ID}",
                    [
                        "MODEL_NAME",
                        "CHARGE_FIELD",
                        "MODEL_TYPE",
                        "AGMT_ID",
                        "MODEL_SEQ",
                    ],
                    rows_by_agmt[header.AGMT_ID],
                )
            )

        if header.AGMT_ID in commitment_rows_by_agmt:
            tables.append(
                _agreement_table(
                    f"AGMT_COMMITMENT - {header.AGMT_ID}",
                    [
                        "COMMITMENT_NAME",
                        "AMOUNT",
                        "COMMITMENT_TYPE",
                        "DIRECTION",
                        "AGMT_ID",
                    ],
                    commitment_rows_by_agmt[header.AGMT_ID],
                )
            )

    return {"partner_name": partner_name, "tables": tables}
