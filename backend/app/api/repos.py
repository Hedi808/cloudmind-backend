from fastapi import APIRouter, HTTPException

from app.agents.repo_analyzer_agent import RepositoryAnalyzerAgent
from app.schemas.repo_analysis import AnalyzeRepoRequest, RepoAnalysisResponse

router = APIRouter(prefix="/repos", tags=["Repositories"])

repo_analyzer = RepositoryAnalyzerAgent()


@router.post("/analyze", response_model=RepoAnalysisResponse)
def analyze_repository(request: AnalyzeRepoRequest):
    try:
        result = repo_analyzer.analyze(
            repo_url=request.repo_url,
            branch=request.branch,
        )

        return result

    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected analysis error: {exc}",
        ) from exc