from kinto.core.errors import ERRORS
from kinto.tests.core.support import FormattedErrorMixin
from kinto.tests.support import BaseWebTest, unittest
from .utils import record_size


class QuotaWebTest(BaseWebTest, unittest.TestCase):

    bucket_uri = '/buckets/test'
    collection_uri = '/buckets/test/collections/col'
    record_uri = '/buckets/test/collections/col/records/rec'
    group_uri = '/buckets/test/groups/grp'

    def create_bucket(self):
        resp = self.app.put(self.bucket_uri, headers=self.headers)
        self.bucket = resp.json['data']

    def create_collection(self):
        resp = self.app.put(self.collection_uri, headers=self.headers)
        self.collection = resp.json['data']

    def create_group(self):
        body = {'data': {'members': ['elle']}}
        resp = self.app.put_json(self.group_uri, body, headers=self.headers)
        self.group = resp.json['data']

    def create_record(self):
        body = {'data': {'foo': 42}}
        resp = self.app.put_json(self.record_uri, body, headers=self.headers)
        self.record = resp.json['data']

    def get_app_settings(self, extra=None):
        settings = super(QuotaWebTest, self).get_app_settings(extra)
        settings['includes'] = 'kinto.plugins.quotas'
        return settings

    def assertStatsEqual(self, data, stats):
        for key in stats:
            assert data[key] == stats[key]


class HelloViewTest(QuotaWebTest):

    def test_quota_capability_if_enabled(self):
        resp = self.app.get('/')
        capabilities = resp.json['capabilities']
        self.assertIn('quotas', capabilities)


class QuotaListenerTest(QuotaWebTest):

    #
    # Bucket
    #
    def test_quota_tracks_bucket_creation(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })

    def test_tracks_bucket_attributes_update(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        body = {'data': {'foo': 'baz'}}
        resp = self.app.patch_json(self.bucket_uri, body,
                                   headers=self.headers)
        storage_size = record_size(resp.json['data'])
        storage_size += record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })

    def test_bucket_delete_destroys_its_quota_entries(self):
        self.create_bucket()
        self.app.delete(self.bucket_uri, headers=self.headers)
        stored_in_backend, _ = self.storage.get_all(parent_id='/buckets/test',
                                                    collection_id='quota')
        assert len(stored_in_backend) == 0

    def test_bucket_delete_doesnt_raise_if_quota_entries_do_not_exist(self):
        self.create_bucket()
        self.storage.delete(parent_id='/buckets/test',
                            collection_id='quota',
                            object_id='bucket_info')
        self.app.delete(self.bucket_uri, headers=self.headers)

    #
    # Collection
    #
    def test_stats_are_not_accessible_if_collection_does_not_exists(self):
        self.create_bucket()
        self.app.get(self.collection_uri, headers=self.headers, status=404)

    def test_quota_tracks_collection_creation(self):
        self.create_bucket()
        self.create_collection()

        # Bucket stats
        storage_size = record_size(self.bucket) + record_size(self.collection)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 0,
            "storage_size": storage_size
        })

        # Collection stats
        storage_size = record_size(self.collection)
        data = self.storage.get("quota", self.collection_uri,
                                "collection_info")
        self.assertStatsEqual(data, {
            "record_count": 0,
            "storage_size": storage_size
        })

    def test_tracks_collection_attributes_update(self):
        self.create_bucket()
        self.create_collection()
        body = {'data': {'foo': 'baz'}}
        resp = self.app.patch_json(self.collection_uri, body,
                                   headers=self.headers)
        # Bucket stats
        storage_size = record_size(self.bucket)
        storage_size += record_size(resp.json['data'])

        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 0,
            "storage_size": storage_size
        })

        # Collection stats
        storage_size -= record_size(self.bucket)
        data = self.storage.get("quota", self.collection_uri,
                                "collection_info")
        self.assertStatsEqual(data, {
            "record_count": 0,
            "storage_size": storage_size
        })

    def test_tracks_collection_delete(self):
        self.create_bucket()
        self.create_collection()
        body = {'data': {'foo': 'baz'}}
        self.app.patch_json(self.collection_uri, body,
                            headers=self.headers)
        self.app.delete(self.collection_uri, headers=self.headers)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 0,
            "record_count": 0,
            "storage_size": record_size(self.bucket)
        })

    def test_collection_delete_destroys_its_quota_entries(self):
        self.create_bucket()
        self.create_collection()
        self.app.delete(self.collection_uri, headers=self.headers)
        stored_in_backend, _ = self.storage.get_all(
            parent_id=self.collection_uri,
            collection_id='quota')
        assert len(stored_in_backend) == 0

    def test_collection_delete_doesnt_raise_if_quota_entries_dont_exist(self):
        self.create_bucket()
        self.create_collection()
        self.storage.delete(parent_id=self.collection_uri,
                            collection_id='quota',
                            object_id='collection_info')
        self.app.delete(self.collection_uri, headers=self.headers)

    def test_tracks_collection_delete_with_multiple_records(self):
        self.create_bucket()
        self.create_collection()
        body = {'data': {'foo': 42}}
        self.app.post_json('%s/records' % self.collection_uri,
                           body, headers=self.headers)
        self.app.post_json('%s/records' % self.collection_uri,
                           body, headers=self.headers)
        self.app.post_json('%s/records' % self.collection_uri,
                           body, headers=self.headers)
        self.app.post_json('%s/records' % self.collection_uri,
                           body, headers=self.headers)
        self.app.delete(self.collection_uri, headers=self.headers)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 0,
            "record_count": 0,
            "storage_size": record_size(self.bucket)
        })

    #
    # Group
    #

    def test_quota_tracks_group_creation(self):
        self.create_bucket()
        self.create_group()
        storage_size = record_size(self.bucket) + record_size(self.group)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 0,
            "record_count": 0,
            "storage_size": storage_size
        })

    def test_tracks_group_attributes_update(self):
        self.create_bucket()
        self.create_group()
        body = {'data': {'foo': 'baz', 'members': ['lui']}}
        resp = self.app.patch_json(self.group_uri, body,
                                   headers=self.headers)
        storage_size = record_size(self.bucket)
        storage_size += record_size(resp.json['data'])
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 0,
            "record_count": 0,
            "storage_size": storage_size
        })

    def test_tracks_group_delete(self):
        self.create_bucket()
        self.create_group()
        self.app.delete(self.group_uri, headers=self.headers)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 0,
            "record_count": 0,
            "storage_size": record_size(self.bucket)
        })

    #
    # Record
    #

    def test_quota_tracks_record_creation(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })

    def test_tracks_record_attributes_update(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        resp = self.app.patch_json(self.record_uri, {'data': {'foo': 'baz'}},
                                   headers=self.headers)
        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(resp.json['data'])
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })

    def test_tracks_record_delete(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        self.app.delete(self.record_uri, headers=self.headers)
        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 0,
            "storage_size": storage_size
        })

    def test_tracks_records_delete_with_multiple_records(self):
        self.create_bucket()
        self.create_collection()
        body = {'data': {'foo': 42}}
        self.app.post_json('%s/records' % self.collection_uri,
                           body, headers=self.headers)
        self.app.post_json('%s/records' % self.collection_uri,
                           body, headers=self.headers)
        self.app.post_json('%s/records' % self.collection_uri,
                           body, headers=self.headers)
        self.app.post_json('%s/records' % self.collection_uri,
                           body, headers=self.headers)
        self.app.delete('%s/records' % self.collection_uri,
                        headers=self.headers)
        storage_size = record_size(self.bucket) + record_size(self.collection)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 0,
            "storage_size": storage_size
        })


class QuotaBucketRecordMixin(object):
    def test_507_is_raised_if_quota_exceeded_on_record_creation(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        body = {'data': {'foo': 42}}
        resp = self.app.post_json('%s/records' % self.collection_uri,
                                  body, headers=self.headers, status=507)

        self.assertFormattedError(
            resp, 507, ERRORS.FORBIDDEN, "Insufficient Storage",
            "There was not enough space to save the resource")

        # Check that the storage was not updated.
        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })


class QuotaBucketUpdateMixin(object):
    def test_507_is_raised_if_quota_exceeded_on_record_update(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        body = {'data': {'foo': 42, 'bar': 'This is a very long string.'}}
        resp = self.app.patch_json(self.record_uri,
                                   body, headers=self.headers, status=507)

        self.assertFormattedError(
            resp, 507, ERRORS.FORBIDDEN, "Insufficient Storage",
            "There was not enough space to save the resource")

        # Check that the storage was not updated.
        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })

    def test_507_is_raised_if_quota_exceeded_on_collection_update(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        body = {'data': {'foo': 42, 'bar': 'This is a very long string.'}}
        resp = self.app.patch_json(self.collection_uri,
                                   body, headers=self.headers, status=507)

        self.assertFormattedError(
            resp, 507, ERRORS.FORBIDDEN, "Insufficient Storage",
            "There was not enough space to save the resource")

        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })

    def test_507_is_raised_if_quota_exceeded_on_group_update(self):
        self.create_bucket()
        self.create_collection()
        body = {'data': {'members': []}}
        resp = self.app.put_json(self.group_uri, body,
                                 headers=self.headers)
        group = resp.json['data']
        body = {'data': {'members': ['elle', 'lui', 'je', 'tu', 'il', 'nous',
                                     'vous', 'ils', 'elles']}}
        resp = self.app.put_json(self.group_uri, body,
                                 headers=self.headers, status=507)

        self.assertFormattedError(
            resp, 507, ERRORS.FORBIDDEN, "Insufficient Storage",
            "There was not enough space to save the resource")

        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(group)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 0,
            "storage_size": storage_size
        })

    def test_507_is_not_raised_if_quota_exceeded_on_record_delete(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        self.app.delete(self.record_uri, headers=self.headers)

        # Check that the storage was not updated.
        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 0,
            "storage_size": storage_size
        })

    def test_507_is_not_raised_if_quota_exceeded_on_collection_delete(self):
        self.create_bucket()
        self.create_collection()
        # fake the quota to the Max
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        data['storage_size'] = 140
        self.storage.update("quota", self.bucket_uri, "bucket_info", data)
        self.app.delete(self.collection_uri,
                        headers=self.headers)

        storage_size = 140
        storage_size -= record_size(self.collection)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 0,
            "record_count": 0,
            "storage_size": storage_size
        })

    def test_507_is_raised_if_quota_exceeded_on_group_delete(self):
        self.create_bucket()
        body = {"data": {"members": []}}
        resp = self.app.put_json(self.group_uri, body, headers=self.headers)
        group = resp.json['data']
        # fake the quota to the Max
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        data['storage_size'] = 140
        self.storage.update("quota", self.bucket_uri, "bucket_info", data)

        self.app.delete(self.group_uri, headers=self.headers)

        storage_size = 140
        storage_size -= record_size(group)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 0,
            "record_count": 0,
            "storage_size": storage_size
        })


class QuotaBucketMixin(object):
    def test_507_is_raised_if_quota_exceeded_on_collection_creation(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        body = {'data': {'foo': 42}}
        resp = self.app.post_json('%s/collections' % self.bucket_uri,
                                  body, headers=self.headers, status=507)

        self.assertFormattedError(
            resp, 507, ERRORS.FORBIDDEN, "Insufficient Storage",
            "There was not enough space to save the resource")

        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })

    def test_507_is_raised_if_quota_exceeded_on_group_creation(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        body = {'data': {'members': ['elle']}}
        resp = self.app.put_json(self.group_uri, body,
                                 headers=self.headers, status=507)

        self.assertFormattedError(
            resp, 507, ERRORS.FORBIDDEN, "Insufficient Storage",
            "There was not enough space to save the resource")

        storage_size = record_size(self.bucket)
        storage_size += record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.bucket_uri, "bucket_info")
        self.assertStatsEqual(data, {
            "collection_count": 1,
            "record_count": 1,
            "storage_size": storage_size
        })


class QuotaMaxBytesExceededSettingsListenerTest(
        FormattedErrorMixin, QuotaBucketRecordMixin, QuotaBucketUpdateMixin,
        QuotaBucketMixin, QuotaWebTest):
    def get_app_settings(self, extra=None):
        settings = super(QuotaMaxBytesExceededSettingsListenerTest,
                         self).get_app_settings(extra)
        settings['quotas.bucket_max_bytes'] = '150'
        return settings


class QuotaMaxBytesExceededBucketSettingsListenerTest(
        FormattedErrorMixin, QuotaBucketRecordMixin, QuotaBucketUpdateMixin,
        QuotaBucketMixin, QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(QuotaMaxBytesExceededBucketSettingsListenerTest,
                         self).get_app_settings(extra)
        settings['quotas.bucket_test_max_bytes'] = '150'
        return settings


class QuotaMaxItemsExceededSettingsListenerTest(
        FormattedErrorMixin, QuotaBucketRecordMixin, QuotaWebTest):
    def get_app_settings(self, extra=None):
        settings = super(QuotaMaxItemsExceededSettingsListenerTest,
                         self).get_app_settings(extra)
        settings['quotas.bucket_max_items'] = '1'
        return settings


class QuotaMaxItemsExceededBucketSettingsListenerTest(
        FormattedErrorMixin, QuotaBucketRecordMixin, QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(QuotaMaxItemsExceededBucketSettingsListenerTest,
                         self).get_app_settings(extra)
        settings['quotas.bucket_test_max_items'] = '1'
        return settings


class QuotaMaxBytesPerItemExceededListenerTest(
        FormattedErrorMixin, QuotaBucketRecordMixin, QuotaBucketUpdateMixin,
        QuotaBucketMixin, QuotaWebTest):
    def get_app_settings(self, extra=None):
        settings = super(QuotaMaxBytesPerItemExceededListenerTest,
                         self).get_app_settings(extra)
        settings['quotas.bucket_max_bytes_per_item'] = '55'
        return settings


class QuotaMaxBytesPerItemExceededBucketListenerTest(
        FormattedErrorMixin, QuotaBucketRecordMixin, QuotaBucketUpdateMixin,
        QuotaBucketMixin, QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(QuotaMaxBytesPerItemExceededBucketListenerTest,
                         self).get_app_settings(extra)
        settings['quotas.bucket_test_max_bytes_per_item'] = '55'
        return settings


class QuotaCollectionMixin(object):
    def test_507_is_raised_if_quota_exceeded_on_record_creation(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        body = {'data': {'foo': 42}}
        resp = self.app.post_json('%s/records' % self.collection_uri,
                                  body, headers=self.headers, status=507)

        self.assertFormattedError(
            resp, 507, ERRORS.FORBIDDEN, "Insufficient Storage",
            "There was not enough space to save the resource")

        # Check that the storage was not updated.
        storage_size = record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.collection_uri,
                                "collection_info")
        self.assertStatsEqual(data, {
            "record_count": 1,
            "storage_size": storage_size
        })


class QuotaCollectionUpdateMixin(object):
    def test_507_is_raised_if_quota_exceeded_on_record_update(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        body = {'data': {'foo': 42, 'bar': 'This is a very long string.'}}
        resp = self.app.patch_json(self.record_uri,
                                   body, headers=self.headers, status=507)

        self.assertFormattedError(
            resp, 507, ERRORS.FORBIDDEN, "Insufficient Storage",
            "There was not enough space to save the resource")

        # Check that the storage was not updated.
        storage_size = record_size(self.collection)
        storage_size += record_size(self.record)
        data = self.storage.get("quota", self.collection_uri,
                                "collection_info")
        self.assertStatsEqual(data, {
            "record_count": 1,
            "storage_size": storage_size
        })

    def test_507_is_not_raised_if_quota_exceeded_on_record_delete(self):
        self.create_bucket()
        self.create_collection()
        self.create_record()
        self.app.delete(self.record_uri, headers=self.headers)

        # Check that the storage was not updated.
        storage_size = record_size(self.collection)
        data = self.storage.get("quota", self.collection_uri,
                                "collection_info")
        self.assertStatsEqual(data, {
            "record_count": 0,
            "storage_size": storage_size
        })


class QuotaMaxBytesExceededCollectionSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaCollectionUpdateMixin,
        QuotaWebTest):
    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxBytesExceededCollectionSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_max_bytes'] = '100'
        return settings


class QuotaMaxBytesExceededCollectionBucketSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaCollectionUpdateMixin,
        QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxBytesExceededCollectionBucketSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_test_max_bytes'] = '100'
        return settings


class QuotaMaxBytesExceededBucketCollectionSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaCollectionUpdateMixin,
        QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxBytesExceededBucketCollectionSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_test_col_max_bytes'] = '100'
        return settings


class QuotaMaxItemsExceededCollectionSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaWebTest):
    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxItemsExceededCollectionSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_max_items'] = '1'
        return settings


class QuotaMaxItemsExceededCollectionBucketSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxItemsExceededCollectionBucketSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_test_max_items'] = '1'
        return settings


class QuotaMaxItemsExceededBucketCollectionSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxItemsExceededBucketCollectionSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_test_col_max_items'] = '1'
        return settings


class QuotaMaxBytesPerItemExceededCollectionSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaWebTest):
    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxBytesPerItemExceededCollectionSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_max_bytes_per_item'] = '80'
        return settings


class QuotaMaxBytesPerItemExceededCollectionBucketSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaCollectionUpdateMixin,
        QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxBytesPerItemExceededCollectionBucketSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_test_max_bytes_per_item'] = '80'
        return settings


class QuotaMaxBytesPerItemExceededBucketCollectionSettingsListenerTest(
        FormattedErrorMixin, QuotaCollectionMixin, QuotaCollectionUpdateMixin,
        QuotaWebTest):

    def get_app_settings(self, extra=None):
        settings = super(
            QuotaMaxBytesPerItemExceededBucketCollectionSettingsListenerTest,
            self).get_app_settings(extra)
        settings['quotas.collection_test_col_max_bytes_per_item'] = '80'
        return settings