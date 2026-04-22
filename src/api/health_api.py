from fastapi import APIRouter, Request

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(request: Request):
    """
    Lightweight liveness / readiness probe.

    Returns the application status and verifies that the database
    connection pool is still reachable.
    """
    db_status = "unavailable"

    try:
        postgres_client = request.app.state.postgres_client
        row = postgres_client.execute_query("SELECT 1")
        if row:
            db_status = "connected"
    except Exception:
        db_status = "unavailable"

    overall = "healthy" if db_status == "connected" else "degraded"

    return {
        "status": overall,
        "database": db_status,
    }
