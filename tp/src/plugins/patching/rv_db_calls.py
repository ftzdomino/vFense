import logging
import logging.config
from time import mktime
from datetime import datetime
from vFense.db.client import db_create_close, r
from vFense.plugins.patching import *
from vFense.plugins.patching._constants import CommonAppKeys
from vFense.plugins.patching.file_data import add_file_data
from vFense.plugins.patching._db import update_customers_in_app_by_app_id, \
    update_app_data_by_app_id
from vFense.plugins.mightymouse import *

from vFense.plugins.vuln import SecurityBulletinKey
import vFense.plugins.vuln.windows.ms as ms
import vFense.plugins.vuln.ubuntu.usn as usn
import vFense.plugins.vuln.cve.cve as cve

from vFense.errorz.error_messages import GenericResults, PackageResults
from vFense.errorz.status_codes import PackageCodes
from vFense.core._constants import CommonKeys
from vFense.core.agent import *
from vFense.operations._constants import AgentOperations
from vFense.core.tag.tagManager import *
from vFense.core.customer import *


logging.config.fileConfig('/opt/TopPatch/conf/logging.config')
logger = logging.getLogger('rvapi')


def update_vulnerability_info_app(
    app_id, app, exists, os_string,
    table=AppCollections.UniqueApplications
    ):

    vuln_info = None
    if app.has_key(AppsKey.AppId):
        app.pop(AppsKey.AppId)
    app[AppsKey.CveIds] = []
    app[AppsKey.VulnerabilityId] = ""
    app[AppsKey.VulnerabilityCategories] = []

    if app[AppsKey.Kb] != "" and os_string.find('Windows') == 0:
        vuln_info = ms.get_vuln_ids(app[AppsKey.Kb])

    elif os_string.find('Ubuntu') == 0:
        vuln_info = (
            usn.get_vuln_ids(
                app[AppsKey.Name],
                app[AppsKey.Version],
                os_string
            )
        )
    if vuln_info:
        app[AppsKey.CveIds] = vuln_info[SecurityBulletinKey.CveIds]
        for cve_id in app[AppsKey.CveIds]:
            #cve_id = cve_id.replace('CVE-', '')
            app[AppsKey.VulnerabilityCategories] += (
                cve.get_vulnerability_categories(cve_id)
            )

        app[AppsKey.VulnerabilityCategories] = (
            list(set(app[AppsKey.VulnerabilityCategories]))
        )
        app[AppsKey.VulnerabilityId] = (
                vuln_info[SecurityBulletinKey.BulletinId]
        )

        if exists:
            update_app_data_by_app_id(app_id, app, table)

    app[AppsKey.AppId] = app_id

    return(app)


@db_create_close
def unique_application_updater(customer_name, app, os_string, conn=None):

    table = AppCollections.UniqueApplications

    exists = None
    try:
        exists = (
            r
            .table(table)
            .get(app[AppsKey.AppId])
            .run(conn)
        )

    except Exception as e:
        logger.exception(e)

    status = app.pop(AppsPerAgentKey.Status, None)
    agent_id = app.pop(AppsPerAgentKey.AgentId, None)
    app.pop(AppsPerAgentKey.InstallDate, None)
    file_data = app.pop(AppsKey.FileData)
    if exists:
        add_file_data(app[AppsKey.AppId], file_data, agent_id)
        update_customers_in_app_by_app_id(customer_name, app[AppsKey.AppId])
        update_vulnerability_info_app(
            exists[AppsKey.AppId], exists, True, os_string
        )

    else:
        add_file_data(app[AppsKey.AppId], file_data, agent_id)
        app[AppsKey.Customers] = [customer_name]
        app[AppsKey.Hidden] = 'no'
        if (len(file_data) > 0 and status == CommonAppKeys.AVAILABLE or
                len(file_data) > 0 and status == CommonAppKeys.INSTALLED):
            app[AppsKey.FilesDownloadStatus] = PackageCodes.FilePendingDownload

        elif len(file_data) == 0 and status == CommonAppKeys.AVAILABLE:
            app[AppsKey.FilesDownloadStatus] = PackageCodes.MissingUri

        elif len(file_data) == 0 and status == CommonAppKeys.INSTALLED:
            app[AppsKey.FilesDownloadStatus] = PackageCodes.FileNotRequired

        app = (
            update_vulnerability_info_app(
                app[AppsKey.AppId], app, False, os_string
            )
        )

        try:
            (
                r
                .table(AppCollections.UniqueApplications)
                .insert(app)
                .run(conn, no_reply=True)
            )

        except Exception as e:
            msg = (
                'Failed to insert %s into unique_applications, error: %s' %
                (app[AppsKey.AppId], e)
            )
            logger.exception(msg)

    return(app, file_data)


@db_create_close
def add_or_update_applications(table=AppCollections.AppsPerAgent, pkg_list=[],
                               delete_afterwards=True, conn=None):
    completed = False
    inserted_count = 0
    updated = None
    replaced_count = 0
    deleted_count = 0
    pkg_count = len(pkg_list)
    last_modified_time = mktime(datetime.now().timetuple())
    if table == AppCollections.AppsPerAgent:
        CurrentAppsPerAgentKey = AppsPerAgentKey
        CurrentAppsPerAgentIndexes = AppsPerAgentIndexes

    elif table == AppCollections.CustomAppsPerAgent:
        CurrentAppsPerAgentKey = CustomAppsPerAgentKey
        CurrentAppsPerAgentIndexes = CustomAppsPerAgentIndexes

    elif table == AppCollections.SupportedAppsPerAgent:
        CurrentAppsPerAgentKey = SupportedAppsPerAgentKey
        CurrentAppsPerAgentIndexes = SupportedAppsPerAgentIndexes

    elif table == AppCollections.vFenseAppsPerAgent:
        CurrentAppsPerAgentKey = AgentAppsPerAgentKey
        CurrentAppsPerAgentIndexes = AgentAppsPerAgentIndexes

    if pkg_count > 0:
        for pkg in pkg_list:
            pkg['last_modified_time'] = r.epoch_time(last_modified_time)

            try:
                app_exists = (
                    r
                    .table(table)
                    .get(pkg[CurrentAppsPerAgentKey.Id])
                    .run(conn)
                )
                if app_exists:
                    updated = (
                        r
                        .table(table)
                        .get(pkg[CurrentAppsPerAgentKey.Id])
                        .update(pkg)
                        .run(conn)
                    )
                else:
                    updated = (
                        r
                        .table(table)
                        .insert(pkg)
                        .run(conn)
                    )
                inserted_count += updated['inserted']
                replaced_count += updated['replaced']

            except Exception as e:
                logger.exception(e)

        try:
            if delete_afterwards:
                deleted = (
                    r
                    .table(table)
                    .get_all(
                        pkg[CurrentAppsPerAgentKey.AgentId],
                        index=CurrentAppsPerAgentIndexes.AgentId
                    )
                    .filter(
                        r.row['last_modified_time'] < r.epoch_time(
                            last_modified_time)
                    )
                    .delete()
                    .run(conn)
                )
                deleted_count += deleted['deleted']
        except Exception as e:
            logger.exception(e)

    return(
        {
            'pass': completed,
            'inserted': inserted_count,
            'replaced': replaced_count,
            'deleted': deleted_count,
            'pkg_count': pkg_count,
        }
    )


@db_create_close
def update_app_per_objectid_and_appid(object_id, app_id, data,
                                      table=AppCollections.AppsPerAgent,
                                      index_to_use=(
                                          AppsPerAgentIndexes.AgentIdAndAppId
                                      ),
                                      conn=None):
    app_updated = None
    try:
        app_updated = (
            r
            .table(table)
            .get_all([object_id, app_id], index=index_to_use)
            .update(data)
            .run(conn)
        )
    except Exception as e:
        logger.exception(e)

    return(app_updated)


@db_create_close
def update_os_app_per_agent(agent_id, app_id, data,
                            table=AppCollections.AppsPerAgent,
                            index_to_use=AppsPerAgentIndexes.AgentIdAndAppId,
                            conn=None):

    return(
        update_app_per_objectid_and_appid(
            agent_id, app_id, data, table, index_to_use
        )
    )


def update_custom_app_per_agent(agent_id, app_id, data,
                                table=AppCollections.CustomAppsPerAgent,
                                index_to_use=(
                                    CustomAppsPerAgentIndexes.AgentIdAndAppId
                                )):
    return(
        update_app_per_objectid_and_appid(
            agent_id, app_id, data, table, index_to_use
        )
    )


def update_supported_app_per_agent(
        agent_id, app_id, data,
        table=AppCollections.SupportedAppsPerAgent,
        index_to_use=SupportedAppsPerAgentIndexes.AgentIdAndAppId
        ):
    return(
        update_app_per_objectid_and_appid(
            agent_id, app_id, data, table, index_to_use
        )
    )


def update_agent_app_per_agent(
        agent_id, app_id, data,
        table=AppCollections.vFenseAppsPerAgent,
        index_to_use=AgentAppsPerAgentIndexes.AgentIdAndAppId
        ):
    return(
        update_app_per_objectid_and_appid(
            agent_id, app_id, data, table, index_to_use
        )
    )



@db_create_close
def delete_app_from_agent(
        app_name, app_version, agent_id,
        table=AppCollections.UniqueApplications,
        per_agent_table=AppCollections.AppsPerAgent,
        index_to_use=AppsIndexes.NameAndVersion,
        per_agent_index=AppsPerAgentIndexes.AgentIdAndAppId,
        conn=None
        ):
    try:
        app_agent_id = list(
            r
            .table(table)
            .get_all([app_name, app_version], index=index_to_use)
            .eq_join(
                lambda x: [agent_id, x[AppsKey.AppId]],
                r.table(per_agent_table),
                index=per_agent_index
            )
            .zip()
            .map(lambda x: x[CommonAppKeys.Id])
            .run(conn)
        )
        if app_agent_id:
            (
                r
                .table(per_agent_table)
                .get(app_agent_id[0])
                .delete()
                .run(conn)
            )

    except Exception as e:
        logger.exception(e)


def delete_custom_app_from_agent(
        app_name, app_version, agent_id,
        table=AppCollections.CustomApps,
        per_agent_table=AppCollections.CustomAppsPerAgent,
        index_to_use=CustomAppsIndexes.NameAndVersion,
        per_agent_index=CustomAppsPerAgentIndexes.AgentIdAndAppId,
        ):
    return(
        delete_app_from_agent(
            app_name, app_version, table,
            per_agent_table, index_to_use,
            per_agent_index
        )
    )


def delete_supported_app_from_agent(
        app_name, app_version, agent_id,
        table=AppCollections.SupportedApps,
        per_agent_table=AppCollections.SupportedAppsPerAgent,
        index_to_use=SupportedAppsIndexes.NameAndVersion,
        per_agent_index=SupportedAppsPerAgentIndexes.AgentIdAndAppId,
        ):
    return(
        delete_app_from_agent(
            app_name, app_version, table,
            per_agent_table, index_to_use,
            per_agent_index
        )
    )


@db_create_close
def get_packages_that_need_to_be_downloaded(conn=None):
    try:
        pkgs = (
            r
            .table(AppCollections.UniqueApplications)
            .filter(
                (r.row[AppsKey.FileDownloadStatus] ==
                    PackageCodes.FilePendingDownload)
                |
                (r.row[AppsKey.FileDownloadStatus] ==
                    PackageCodes.FileFailedDownload)
                |
                (r.row[AppsKey.FileDownloadStatus] ==
                    PackageCodes.HashNotVerified)
            )
            .pluck(AppsKey.AppId. AppsKey.FileData, AppsKey.OsCode)
            .run(conn)
        )
    except Exception as e:
        pkgs = []
        logger.exception(e)

    return(pkgs)


@db_create_close
def update_hidden_status(username, customer_name,
                         uri, method, app_ids, hidden='yes',
                         table=AppCollections.UniqueApplications, conn=None):
    if table == AppCollections.UniqueApplications:
        CurrentAppsKey = AppsKey

    elif table == AppCollections.CustomApps:
        CurrentAppsKey = CustomAppsKey

    elif table == AppCollections.SupportedApps:
        CurrentAppsKey = SupportedAppsKey

    elif table == AppCollections.vFenseAppsPerAgent:
        CurrentAppsKey = AgentAppsKey

    try:
        if hidden == CommonKeys.YES or hidden == CommonKeys.NO:
            (
                r
                .expr(app_ids)
                .for_each(
                    lambda app_id:
                    r
                    .table(table)
                    .get(app_id)
                    .update(
                        {
                            CurrentAppsKey.Hidden: hidden
                        }
                    )
                )
                .run(conn)
            )
        elif hidden == 'toggle':
            for app_id in app_ids:
                toggled = (
                    r
                    .table(table)
                    .get(app_id)
                    .update(
                        {
                            CurrentAppsKey.Hidden: (
                                r.branch(
                                    r.row[CurrentAppsKey.Hidden] == CommonKeys.YES,
                                    CommonKeys.NO,
                                    CommonKeys.YES
                                )
                            )
                        }
                    )
                    .run(conn)
                )

        results = (
            PackageResults(
                username, uri, method
            ).toggle_hidden(app_ids, hidden)
        )

    except Exception as e:
        logger.exception(e)
        results = (
            GenericResults(
                username, uri, method
            ).something_broke(app_ids, 'toggle hidden on os_apps', e)
        )

    return(results)


@db_create_close
def get_all_app_stats_by_tagid(username, customer_name,
                               uri, method, tag_id, conn=None):
    data = []
    try:
        inventory = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.INSTALLED,
                    x[AppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.AppsPerAgent),
                index=AppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: inventory,
                CommonAppKeys.STATUS: CommonAppKeys.INSTALLED,
                CommonAppKeys.NAME: CommonAppKeys.SOFTWAREINVENTORY
            }
        )
        os_apps_avail = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.AVAILABLE,
                    x[AppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.AppsPerAgent),
                index=AppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: os_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.OS
            }
        )
        custom_apps_avail = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.AVAILABLE,
                    x[CustomAppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.CustomAppsPerAgent),
                index=CustomAppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: custom_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.CUSTOM
            }
        )
        supported_apps_avail = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.AVAILABLE,
                    x[SupportedAppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.SupportedAppsPerAgent),
                index=SupportedAppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: supported_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.SUPPORTED
            }
        )
        agent_apps_avail = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.AVAILABLE,
                    x[AgentAppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.vFenseAppsPerAgent),
                index=AgentAppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: agent_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.AGENT_UPDATES
            }
        )

       # all_pending_apps = (
       #    r
       #    .table(TagsPerAgentCollection, use_outdated=True)
       #    .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
       #    .pluck(TagsPerAgentKey.AgentId)
       #    .eq_join(
       #        lambda x: [
       #            PENDING,
       #            x[AppsPerAgentKey.AgentId]
       #        ],
       #        r.table(AppCollections.AppsPerAgent),
       #        index=AppsPerAgentIndexes.StatusAndAgentId
       #    )
       #    .pluck({'right': AppsPerAgentKey.AppId})
       #    .distinct()
       #    .count()
       #    .run(conn)
       #)

       #data.append(
       #    {
       #        CommonAppKeys.COUNT: all_pending_apps,
       #        CommonAppKeys.STATUS: CommonAppKeys.PENDING,
       #        CommonAppKeys.NAME: CommonAppKeys.PENDING.capitalize()
       #    }
       #)

        results = (
            GenericResults(
                username, uri, method
            ).information_retrieved(data, len(data))
        )

        logger.info(results)

    except Exception as e:
        results = (
            GenericResults(
                username, uri, method
            ).something_broke('getting_pkg_stats', 'updates', e)
        )
        logger.exception(results)

    return(results)


@db_create_close
def get_all_avail_stats_by_tagid(username, customer_name,
                                 uri, method, tag_id, conn=None):
    data = []
    try:
        os_apps_avail = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.AVAILABLE,
                    x[AppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.AppsPerAgent),
                index=AppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: os_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.OS
            }
        )
        custom_apps_avail = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.AVAILABLE,
                    x[CustomAppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.CustomAppsPerAgent),
                index=CustomAppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: custom_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.CUSTOM
            }
        )
        supported_apps_avail = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.AVAILABLE,
                    x[SupportedAppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.SupportedAppsPerAgent),
                index=SupportedAppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: supported_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.SUPPORTED
            }
        )
        agent_apps_avail = (
            r
            .table(TagsPerAgentCollection, use_outdated=True)
            .get_all(tag_id, index=TagsPerAgentIndexes.TagId)
            .pluck(TagsPerAgentKey.AgentId)
            .eq_join(
                lambda x: [
                    CommonAppKeys.AVAILABLE,
                    x[AgentAppsPerAgentKey.AgentId]
                ],
                r.table(AppCollections.vFenseAppsPerAgent),
                index=AgentAppsPerAgentIndexes.StatusAndAgentId
            )
            .pluck({'right': AppsPerAgentKey.AppId})
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: agent_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.AGENT_UPDATES
            }
        )

        results = (
            GenericResults(
                username, uri, method
            ).information_retrieved(data, len(data))
        )

        logger.info(results)

    except Exception as e:
        results = (
            GenericResults(
                username, uri, method
            ).something_broke('getting_pkg_stats', 'updates', e)
        )
        logger.exception(results)

    return(results)


@db_create_close
def get_all_app_stats_by_customer(username, customer_name,
                                  uri, method, conn=None):
    data = []
    try:
        os_apps_avail = (
            r
            .table(AppCollections.AppsPerAgent, use_outdated=True)
            .get_all(
                [
                    CommonAppKeys.AVAILABLE, customer_name
                ],
                index=AppsPerAgentIndexes.StatusAndCustomer
            )
            .pluck(AppsPerAgentKey.AppId)
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: os_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.OS
            }
        )
        custom_apps_avail = (
            r
            .table(AppCollections.CustomAppsPerAgent, use_outdated=True)
            .get_all(
                [
                    CommonAppKeys.AVAILABLE, customer_name
                ],
                index=CustomAppsPerAgentIndexes.StatusAndCustomer
            )
            .pluck(CustomAppsPerAgentKey.AppId)
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: custom_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.CUSTOM
            }
        )
        supported_apps_avail = (
            r
            .table(AppCollections.SupportedAppsPerAgent, use_outdated=True)
            .get_all(
                [
                    CommonAppKeys.AVAILABLE, customer_name
                ],
                index=SupportedAppsPerAgentIndexes.StatusAndCustomer
            )
            .pluck(SupportedAppsPerAgentKey.AppId)
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: supported_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.SUPPORTED
            }
        )
        agent_apps_avail = (
            r
            .table(AppCollections.vFenseAppsPerAgent, use_outdated=True)
            .get_all(
                [
                    CommonAppKeys.AVAILABLE, customer_name
                ],
                index=AgentAppsPerAgentIndexes.StatusAndCustomer
            )
            .pluck(AgentAppsPerAgentKey.AppId)
            .distinct()
            .count()
            .run(conn)
        )
        data.append(
            {
                CommonAppKeys.COUNT: agent_apps_avail,
                CommonAppKeys.STATUS: CommonAppKeys.AVAILABLE,
                CommonAppKeys.NAME: CommonAppKeys.AGENT_UPDATES
            }
        )

        all_pending_apps = (
            r
            .table(AppCollections.AppsPerAgent, use_outdated=True)
            .get_all(
                [
                    CommonAppKeys.PENDING, customer_name
                ],
                index=AppsPerAgentIndexes.StatusAndCustomer
            )
            .pluck((CommonAppKeys.APP_ID))
            .distinct()
            .count()
            .run(conn)
        )

        data.append(
            {
                CommonAppKeys.COUNT: all_pending_apps,
                CommonAppKeys.STATUS: CommonAppKeys.PENDING,
                CommonAppKeys.NAME: CommonAppKeys.PENDING.capitalize()
            }
        )

        results = (
            GenericResults(
                username, uri, method
            ).information_retrieved(data, len(data))
        )

        logger.info(results)

    except Exception as e:
        results = (
            GenericResults(
                username, uri, method
            ).something_broke('getting_pkg_stats', 'updates', e)
        )
        logger.exception(results)

    return(results)


@db_create_close
def delete_app_from_rv(
        app_id,
        table=AppCollections.UniqueApplications,
        per_agent_table=AppCollections.AppsPerAgent,
        conn=None
        ):
    completed = True
    try:
        (
            r
            .table(table)
            .filter({AppsKey.AppId: app_id})
            .delete()
            .run(conn)
        )
        (
            r
            .table(per_agent_table)
            .filter({AppsKey.AppId: app_id})
            .delete()
            .run(conn)
        )
        if table == AppCollections.CustomApps:
            (
                r
                .table(FileCollections.Files)
                .filter(lambda x: x[FilesKey.AppIds].contains(app_id))
                .delete()
                .run(conn)
            )

    except Exception as e:
        logger.exception(e)
        completed = False

    return(completed)


def update_app_status(agent_id, app_id, oper_type, data):
    if oper_type == AgentOperations.INSTALL_OS_APPS or oper_type == UNINSTALL:
        update_os_app_per_agent(agent_id, app_id, data)

    elif oper_type == AgentOperations.INSTALL_CUSTOM_APPS:
        update_custom_app_per_agent(agent_id, app_id, data)

    elif oper_type == AgentOperations.INSTALL_SUPPORTED_APPS:
        update_supported_app_per_agent(agent_id, app_id, data)

    elif oper_type == AgentOperations.INSTALL_AGENT_APPS:
        update_agent_app_per_agent(agent_id, app_id, data)

