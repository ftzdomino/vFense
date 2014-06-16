import json
import logging
import logging.config
from vFense import VFENSE_LOGGING_CONFIG

from vFense.core._constants import CPUThrottleValues
from vFense.core.api._constants import ApiArguments, ApiValues
from vFense.core.api.base import BaseHandler
from vFense.core.decorators import (
    authenticated_request, convert_json_to_arguments
)

from vFense.core.permissions._constants import Permissions
from vFense.core.permissions.permissions import (
    verify_permission_for_user, return_results_for_permissions
)

from vFense.core.permissions.decorators import check_permissions
from vFense.core.agent import *
from vFense.core.user._constants import DefaultUsers
from vFense.core.agent.agents import (
    change_view_for_all_agents_in_view, remove_all_agents_for_view
)

from vFense.core.user._db_model import UserKeys
from vFense.core.view._db_model import ViewKeys
from vFense.core.view import View
from vFense.core.view.manager import ViewManager
from vFense.core.view.search.search import RetrieveViews

from vFense.core.operations.decorators import log_operation
from vFense.core.operations._admin_constants import AdminActions
from vFense.core.operations._constants import vFenseObjects

from vFense.errorz._constants import ApiResultKeys
from vFense.errorz.error_messages import GenericResults
from vFense.errorz.status_codes import ViewFailureCodes, ViewCodes
from vFense.plugins.patching.patching import (
    remove_all_apps_for_view, change_view_for_apps_in_view
)

from vFense.errorz.status_codes import (
    GenericCodes, GenericFailureCodes
)

logging.config.fileConfig(VFENSE_LOGGING_CONFIG)
logger = logging.getLogger('rvapi')


class ViewHandler(BaseHandler):

    @authenticated_request
    @check_permissions(Permissions.ADMINISTRATOR)
    def get(self, view_name):
        active_user = self.get_current_user()
        uri = self.request.uri
        http_method = self.request.method
        user = UserManager(active_user)
        self.is_global = user.get_attribute(UserKeys.Global)
        self.current_view = user.get_attribute(UserKeys.CurrentView)
        try:
            results = self.get_view(view_name)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            results = (
                GenericResults(
                    active_user, uri, http_method
                ).something_broke(active_user, 'User', e)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        @results_message
        def get_view(self, view):
            if self.is_global:
                fetch_views = RetrieveViews()
            else:
                fetch_views = RetrieveViews(parent_view=self.current_view)

            results = fetch_views.by_name(views)
            return results


    @authenticated_request
    @convert_json_to_arguments
    @check_permissions(Permissions.ADMINISTRATOR)
    def post(self, view_name):
        active_user = self.get_current_user()
        uri = self.request.uri
        http_method = self.request.method
        self.view = ViewManager(view_name)
        try:
            action = self.arguments.get(ApiArguments.ACTION, ApiValues.ADD)
            ### Add Users to this view or Remove users from this view
            usernames = self.arguments.get(ApiArguments.USERNAMES, None)
            if not isinstance(usernames, list) and isinstance(usernames, str):
                usernames = usernames.split(',')

            if usernames:
                if action == ApiValues.ADD:
                    results = self.add_users(usernames)

                elif action == ApiValues.DELETE:
                    results = self.remove_users(usernames)

            ### Add groups to this view or Remove groups from this view
            group_ids = self.arguments.get(ApiArguments.GROUP_IDS, None)
            if not isinstance(group_ids, list) and isinstance(group_ids, str):
                group_ids = group_ids.split(',')

            if group_ids:
                if action == ApiValues.ADD:
                    results = self.add_groups(group_ids)

                elif action == ApiValues.DELETE:
                    results = self.remove_groups(group_ids)

            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            results = (
                GenericResults(
                    active_user, uri, http_method
                ).something_broke(active_user, 'Views', e)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        @log_operation(AdminActions.ADD_USERS_TO_VIEW, vFenseObjects.VIEW)
        @results_message
        def add_users(self, users):
            results = self.view.add_users(users)
            return results

        @log_operation(AdminActions.ADD_GROUPS_TO_VIEW, vFenseObjects.VIEW)
        @results_message
        def add_groups(self, group_ids):
            results = self.view.add_groups(group_ids)
            return results

        @log_operation(AdminActions.REMOVE_USERS_FROM_VIEW, vFenseObjects.VIEW)
        @results_message
        def remove_users(self, users):
            results = self.view.remove_users(users)
            return results

        @log_operation(AdminActions.REMOVE_GROUPS_FROM_VIEW, vFenseObjects.VIEW)
        @results_message
        def remove_groups(self, group_ids):
            results = self.view.remove_groups(group_ids)
            return results


    @authenticated_request
    @convert_json_to_arguments
    @check_permissions(Permissions.ADMINISTRATOR)
    def put(self, view_name):
        active_user = self.get_current_user()
        uri = self.request.uri
        http_method = self.request.method
        self.view = ViewManager(view_name)
        results = {}
        data = []
        try:
            net_throttle = self.arguments.get(ApiArguments.NET_THROTTLE, None)
            cpu_throttle = self.arguments.get(ApiArguments.CPU_THROTTLE, None)
            server_queue_ttl = self.arguments.get(ApiArguments.SERVER_QUEUE_TTL, None)
            agent_queue_ttl = self.arguments.get(ApiArguments.AGENT_QUEUE_TTL, None)
            download_url = self.arguments.get(ApiArguments.DOWNLOAD_URL, None)

            if net_throttle:
                results = self.edit_net_throttle(net_throttle)
                if results.get(ApiResultKeys.DATA, None):
                    data.append(results.get(ApiResultKeys.DATA))

            if cpu_throttle:
                results = self.edit_cpu_throttle(cpu_throttle)
                if results.get(ApiResultKeys.DATA, None):
                    data.append(results.get(ApiResultKeys.DATA))

            if server_queue_ttl:
                results = self.edit_server_queue_ttl(server_queue_ttl)
                if results.get(ApiResultKeys.DATA, None):
                    data.append(results.get(ApiResultKeys.DATA))

            if agent_queue_ttl:
                results = self.edit_agent_queue_ttl(agent_queue_ttl)
                if results.get(ApiResultKeys.DATA, None):
                    data.append(results.get(ApiResultKeys.DATA))

            if download_url:
                results = self.edit_download_url(download_url)
                if results.get(ApiResultKeys.DATA, None):
                    data.append(results.get(ApiResultKeys.DATA))

            results[ApiResultKeys.DATA] = data

            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            results = (
                GenericResults(
                    active_user, uri, http_method
                ).something_broke(active_user, 'Views', e)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        @log_operation(AdminActions.EDIT_NET_THROTTLE, vFenseObjects.VIEW)
        @results_message
        def edit_net_throttle(self, net_throttle):
            results = self.view.edit_net_throttle(net_throttle)
            return results

        @log_operation(AdminActions.EDIT_CPU_THROTTLE, vFenseObjects.VIEW)
        @results_message
        def edit_cpu_throttle(self, cpu_throttle):
            results = self.view.edit_cpu_throttle(cpu_throttle)
            return results

        @log_operation(AdminActions.EDIT_SERVER_QUEUE_TTL, vFenseObjects.VIEW)
        @results_message
        def edit_server_queue_ttl(self, server_queue_ttl):
            results = self.view.edit_server_queue_ttl(server_queue_ttl)
            return results

        @log_operation(AdminActions.EDIT_AGENT_QUEUE_TTL, vFenseObjects.VIEW)
        @results_message
        def edit_agent_queue_ttl(self, agent_queue_ttl):
            results = self.view.edit_agent_queue_ttl(agent_queue_ttl)
            return results

        @log_operation(AdminActions.EDIT_DOWNLOAD_URL, vFenseObjects.VIEW)
        @results_message
        def edit_download_url(self, package_download_url):
            results = self.view.edit_download_url(package_download_url)
            return results


    @authenticated_request
    @convert_json_to_arguments
    @check_permissions(Permissions.ADMINISTRATOR)
    def delete(self, view_name):
        active_user = self.get_current_user()
        uri = self.request.uri
        http_method = self.request.method
        self.view = ViewManager(view_name)
        try:
            deleted_agents = (
                self.arguments.get(ApiArguments.DELETE_ALL_AGENTS)
            )
            move_agents_to_view = (
                self.arguments.get(ApiArguments.MOVE_AGENTS_TO_VIEW, None)
            )
            results = self.remove_view()

            if move_agents_to_view:
                if (results[ApiResultKeys.VFENSE_STATUS_CODE] ==
                        ViewCodes.ViewDeleted):

                    change_view_for_all_agents_in_view(
                        view_name, move_agents_to_view
                    )
                    change_view_for_apps_in_view(
                        view_name, move_agents_to_view
                    )

            elif deleted_agents == ApiValues.YES:
                if (results[ApiResultKeys.VFENSE_STATUS_CODE] ==
                        ViewCodes.ViewDeleted):

                    remove_all_agents_for_view(view_name)
                    remove_all_apps_for_view(view_name)

            else:
                results = (
                    GenericResults(
                        active_user, uri, http_method
                    ).incorrect_arguments()
                )
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            results = (
                GenericResults(
                    active_user, uri, http_method
                ).something_broke(active_user, 'User', e)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        @log_operation(AdminActions.REMOVE_VIEW, vFenseObjects.VIEW)
        @results_message
        def remove_view(self):
            results = self.view.edit_download_url(view)
            return results


class ViewsHandler(BaseHandler):

    @authenticated_request
    @check_permissions(Permissions.ADMINISTRATOR)
    def get(self):
        active_user = self.get_current_user()
        uri = self.request.uri
        method = self.request.method
        all_views = None
        user = UserManager(active_user)
        #active_view = user.get_attribute(UserKeys.CurrentView)
        is_global = user.get_attribute(UserKeys.Global)
        view_context = self.get_argument('view_context', None)
        parent_view = self.get_argument('parent_view', None)
        query = self.get_argument('query', None)
        count = int(self.get_argument('count', 30))
        offset = int(self.get_argument('offset', 0))
        sort = self.get_argument('sort', 'asc')
        sort_by = self.get_argument('sort_by', ViewKeys.ViewName)
        self.fetch_views = (
            RetrieveViews(
                parent_view, count, offset, sort, sort_by, is_global
            )
        )
        if not view_context and active_user == DefaultUsers.GLOBAL_ADMIN:
            all_views = True

        try:
            if view_context:
                granted, status_code = (
                    verify_permission_for_user(
                        active_user, Permissions.ADMINISTRATOR, view_context
                    )
                )
            else:
                granted, status_code = (
                    verify_permission_for_user(
                        active_user, Permissions.ADMINISTRATOR
                    )
                )
            if granted and not all_views and not view_context:
                results = self.get_all_views_for_user(active_user)

            elif granted and all_views and not view_context:
                results = self.get_all_views()

            elif granted and view_context and not all_views:
                results = self.get_view(view_context)

            elif granted and regex:
                results = self.get_all_views_by_regex(query)

            elif not granted:
                results = (
                    return_results_for_permissions(
                        active_user, granted, status_code,
                        Permissions.ADMINISTRATOR, uri, method
                    )
                )

            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            results = (
                GenericResults(
                    active_user, uri, method
                ).something_broke(active_user, 'Views', e)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        @results_message
        def get_all_views(self):
            results = self.fetch_views.all()
            return results

        @results_message
        def get_all_views_for_user(self, username):
            results = self.fetch_views.for_user(username)
            return results

        @results_message
        def get_all_views_by_regex(self, regex):
            results = self.fetch_views.by_regex(regex)
            return results

        @results_message
        def get_view(self, view_name):
            results = self.fetch_views.by_name(view_name)
            return results


    @authenticated_request
    @convert_json_to_arguments
    @check_permissions(Permissions.ADMINISTRATOR)
    def post(self):
        active_user = self.get_current_user()
        uri = self.request.uri
        http_method = self.request.method
        active_view = user.get_attribute(UserKeys.CurrentView)
        try:
            self.parent_view = self.get_argument('view_context', active_view)
            self.view_name = (
                self.arguments.get(ApiArguments.VIEW_NAME)
            )
            self.pkg_url = (
                self.arguments.get(ApiArguments.DOWNLOAD_URL, None)
            )
            self.net_throttle = (
                self.arguments.get(ApiArguments.NET_THROTTLE, 0)
            )
            self.cpu_throttle = (
                self.arguments.get(
                    ApiArguments.CPU_THROTTLE, CPUThrottleValues.NORMAL
                )
            )
            self.server_queue_ttl = (
                self.arguments.get(ApiArguments.SERVER_QUEUE_TTL, 10)
            )
            self.agent_queue_ttl = (
                self.arguments.get(ApiArguments.AGENT_QUEUE_TTL, 10)
            )

            results = self.create_view()

            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        except Exception as e:
            results = (
                GenericResults(
                    active_user, uri, http_method
                ).something_broke(self.active_user, 'User', e)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        @log_operation(AdminActions.CREATE_VIEW, vFenseObjects.VIEW)
        @results_message
        def create_view(self):
            view = View(
                self.view_name, self.parent_view,
                users=[self.active_users],
                net_throttle=self.net_throttle,
                cpu_throttle=self.cpu_throttle,
                server_queue_ttl=self.server_queue_ttl,
                agent_queue_ttl=self.agent_queue_ttl,
                package_download_url=self.pkg_url
            )
            manager = ViewManager(view.name)
            results = manager.create(view)
            return results


    @authenticated_request
    @convert_json_to_arguments
    @check_permissions(Permissions.ADMINISTRATOR)
    def delete(self):
        active_user = self.get_current_user()
        uri = self.request.uri
        method = self.request.method
        try:
            view_names = (
                self.arguments.get(ApiArguments.VIEW_NAMES)
            )

            if not isinstance(view_names, list):
                view_names = view_names.split(',')

            results = (
                remove_views(
                    view_names,
                    active_user, uri, method
                )
            )
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

            if (results[ApiResultKeys.VFENSE_STATUS_CODE] ==
                    ViewCodes.ViewDeleted):

                remove_all_agents_for_view(view_name)
                remove_all_apps_for_view(view_name)

        except Exception as e:
            results = (
                GenericResults(
                    active_user, uri, method
                ).something_broke(active_user, 'User', e)
            )
            logger.exception(e)
            self.set_status(results['http_status'])
            self.set_header('Content-Type', 'application/json')
            self.write(json.dumps(results, indent=4))

        @log_operation(AdminActions.REMOVE_VIEWS, vFenseObjects.VIEWS)
        @results_message
        def remove_views(self, view_names):
            end_results = {}
            views_deleted = []
            views_unchanged = []
            for view_name in view_names:
                manager = ViewManager(view_name)
                results = manager.remove()
                if (results[ApiResultKeys.VFENSE_STATUS_CODE]
                        == ViewCodes.Deleted):
                    views_deleted.append(view_name)
                else:
                    views_unchanged.append(view_name)

            end_results[ApiResultKeys.UNCHANGED_IDS] = views_unchanged
            end_results[ApiResultKeys.DELETED_IDS] = views_deleted
            if views_unchanged and views_deleted:
                msg = (
                    'view names deleted: %s, view names unchanged: %s'
                    % (', '.join(views_deleted), ', '.join(views_unchanged))
                )
                end_results[ApiResultKeys.GENERIC_STATUS_CODE] = (
                    GenericFailureCodes.FailedToDeleteAllObjects
                )
                end_results[ApiResultKeys.VFENSE_STATUS_CODE] = (
                    ViewFailureCodes.FailedToDeleteAllViews
                )
                end_results[ApiResultKeys.MESSAGE] = msg

            elif views_deleted and not views_unchanged:
                msg = (
                    'view names deleted: %s'
                    % (', '.join(views_deleted))
                )
                end_results[ApiResultKeys.GENERIC_STATUS_CODE] = (
                    GenericCodes.ObjectsDeleted
                )
                end_results[ApiResultKeys.VFENSE_STATUS_CODE] = (
                    ViewCodes.ViewsDeleted
                )
                end_results[ApiResultKeys.MESSAGE] = msg

            elif views_unchanged and not views_deleted:
                msg = (
                    'view names unchanged: %s'
                    % (', '.join(views_unchanged))
                )
                end_results[ApiResultKeys.GENERIC_STATUS_CODE] = (
                    GenericCodes.ObjectsUnchanged
                )
                end_results[ApiResultKeys.VFENSE_STATUS_CODE] = (
                    ViewCodes.ViewsUnchanged
                )
                end_results[ApiResultKeys.MESSAGE] = msg

            return end_results

