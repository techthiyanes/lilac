"""Serves the Lilac server."""

import logging
import os
import shutil
import subprocess
from typing import Any, Optional

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import (
  router_concept,
  router_data_loader,
  router_dataset,
  router_google_login,
  router_signal,
  router_tasks,
)
from .auth import AuthenticationInfo, UserInfo, get_user_access
from .concepts.db_concept import DiskConceptDB, get_concept_output_dir
from .config import CONFIG, data_path
from .router_utils import RouteErrorHandler
from .tasks import task_manager
from .utils import get_dataset_output_dir, list_datasets

DIST_PATH = os.path.abspath(os.path.join('web', 'blueprint', 'build'))
LILAC_AUTH_ENABLED = CONFIG.get('LILAC_AUTH_ENABLED', False)
LILAC_OAUTH_SECRET_KEY = CONFIG.get('LILAC_OAUTH_SECRET_KEY', None)
if LILAC_AUTH_ENABLED and not LILAC_OAUTH_SECRET_KEY:
  raise ValueError('`LILAC_OAUTH_SECRET_KEY` must be set if `LILAC_AUTH_ENABLED` is True.')

tags_metadata: list[dict[str, Any]] = [{
  'name': 'datasets',
  'description': 'API for querying a dataset.',
}, {
  'name': 'concepts',
  'description': 'API for managing concepts.',
}, {
  'name': 'data_loaders',
  'description': 'API for loading data.',
}, {
  'name': 'signals',
  'description': 'API for managing signals.',
}]


def custom_generate_unique_id(route: APIRoute) -> str:
  """Generate the name for the API endpoint."""
  return route.name


app = FastAPI(
  default_response_class=ORJSONResponse,
  generate_unique_id_function=custom_generate_unique_id,
  openapi_tags=tags_metadata)
app.add_middleware(SessionMiddleware, secret_key=LILAC_OAUTH_SECRET_KEY)
app.include_router(router_google_login.router, prefix='/google', tags=['google_login'])

v1_router = APIRouter(route_class=RouteErrorHandler)
v1_router.include_router(router_dataset.router, prefix='/datasets', tags=['datasets'])
v1_router.include_router(router_concept.router, prefix='/concepts', tags=['concepts'])
v1_router.include_router(router_data_loader.router, prefix='/data_loaders', tags=['data_loaders'])
v1_router.include_router(router_signal.router, prefix='/signals', tags=['signals'])
v1_router.include_router(router_tasks.router, prefix='/tasks', tags=['tasks'])


@app.get('/auth_info')
def auth_info(request: Request) -> AuthenticationInfo:
  """Returns the user's ACLs.

  NOTE: Validation happens server-side as well. This is just used for UI treatment.
  """
  user_info: Optional[UserInfo] = None
  if LILAC_AUTH_ENABLED:
    session_user = request.session.get('user', None)
    if session_user:
      user_info = UserInfo(
        email=session_user['email'],
        name=session_user['name'],
        given_name=session_user['given_name'],
        family_name=session_user['family_name'])

  return AuthenticationInfo(
    user=user_info, access=get_user_access(), auth_enabled=LILAC_AUTH_ENABLED)


app.include_router(v1_router, prefix='/api/v1')


@app.api_route('/{path_name}', include_in_schema=False)
def catch_all() -> FileResponse:
  """Catch any other requests and serve index for HTML5 history."""
  return FileResponse(path=os.path.join(DIST_PATH, 'index.html'))


# Serve static files in production mode.
app.mount('/', StaticFiles(directory=DIST_PATH, html=True, check_dir=False))


@app.on_event('startup')
def startup() -> None:
  """Download dataset files from the HF space that was uploaded before building the image."""
  # SPACE_ID is the HuggingFace Space ID environment variable that is automatically set by HF.
  repo_id = CONFIG.get('SPACE_ID', None)

  if repo_id:
    # Copy datasets.
    spaces_data_dir = os.path.join('data')
    datasets = list_datasets(spaces_data_dir)
    for dataset in datasets:
      spaces_dataset_output_dir = get_dataset_output_dir(spaces_data_dir, dataset.namespace,
                                                         dataset.dataset_name)
      persistent_output_dir = get_dataset_output_dir(data_path(), dataset.namespace,
                                                     dataset.dataset_name)
      shutil.rmtree(persistent_output_dir, ignore_errors=True)
      shutil.copytree(spaces_dataset_output_dir, persistent_output_dir, dirs_exist_ok=True)
      shutil.rmtree(spaces_dataset_output_dir, ignore_errors=True)

    # Copy concepts.
    concepts = DiskConceptDB(spaces_data_dir).list()
    for concept in concepts:
      spaces_concept_output_dir = get_concept_output_dir(spaces_data_dir, concept.namespace,
                                                         concept.name)
      persistent_output_dir = get_concept_output_dir(data_path(), concept.namespace, concept.name)
      shutil.rmtree(persistent_output_dir, ignore_errors=True)
      shutil.copytree(spaces_concept_output_dir, persistent_output_dir, dirs_exist_ok=True)
      shutil.rmtree(spaces_concept_output_dir, ignore_errors=True)


def run(cmd: str) -> subprocess.CompletedProcess[bytes]:
  """Run a command and return the result."""
  return subprocess.run(cmd, shell=True, check=True)


@app.on_event('shutdown')
async def shutdown_event() -> None:
  """Kill the task manager when FastAPI shuts down."""
  await task_manager().stop()


class GetTasksFilter(logging.Filter):
  """Task filter for /tasks."""

  def filter(self, record: logging.LogRecord) -> bool:
    """Filters out /api/v1/tasks/ from the logs."""
    return record.getMessage().find('/api/v1/tasks/') == -1


logging.getLogger('uvicorn.access').addFilter(GetTasksFilter())