# -*- coding: UTF-8 -*-
#
# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests to cover the adwords module."""

import io
import os
import StringIO
import sys
import tempfile
import unittest
import urllib
import urllib2
from xml.etree import ElementTree


import googleads.adwords
import googleads.common
import googleads.errors
import mock
import suds


PYTHON2 = sys.version_info[0] == 2
URL_REQUEST_PATH = ('urllib2' if PYTHON2 else 'urllib.request')
CURRENT_VERSION = sorted(googleads.adwords._SERVICE_MAP.keys())[-1]


def GetAdWordsClient(**kwargs):
  """Returns an initialized AdwordsClient for use in testing.

  If not specified, the keyword arguments will be set to default test values.

  Args:
    **kwargs: Optional keyword arguments that can be provided to customize the
      generated AdWordsClient.
  Keyword Arguments:
    ccid: A str value for the AdWordsClient's client_customer_id.
    dev_token: A str value for the AdWordsClient's developer_token.
    oauth2_client: A GoogleOAuth2Client instance or mock implementing its
      interface.
    proxy_config: A googleads.common.ProxyConfig instance. If not specified,
      this will default to None to specify that no Proxy is being used.
    report_downloader_headers: A dict containing optional report downloader
      headers.
    user_agent: A str value for the AdWordsClient's user_agent.

  Returns:
    An AdWordsClient instance intended for testing.
  """
  client_customer_id = kwargs.get('ccid', 'client customer id')
  dev_token = kwargs.get('dev_token', 'dev_token')
  user_agent = kwargs.get('user_agent', 'user_agent')
  validate_only = kwargs.get('validate_only', False)
  partial_failure = kwargs.get('partial_failure', False)
  report_downloader_headers = kwargs.get('report_downloader_headers', {})

  if 'oauth2_client' in kwargs:
    oauth2_client = kwargs['oauth2_client']
  else:
    oauth_header = {'Authorization': 'header'}
    oauth2_client = mock.Mock()
    oauth2_client.CreateHttpHeader.return_value = dict(oauth_header)

  client = googleads.adwords.AdWordsClient(
      dev_token, oauth2_client, user_agent,
      client_customer_id=client_customer_id,
      cache=kwargs.get('cache'),
      proxy_config=kwargs.get('proxy_config'),
      validate_only=validate_only, partial_failure=partial_failure,
      report_downloader_headers=report_downloader_headers)

  return client


def GetProxyConfig(http_host=None, http_port=None, https_host=None,
                   https_port=None, cafile=None,
                   disable_certificate_validation=None):
  """Returns an initialized ProxyConfig for use in testing.

  Args:
    http_host: A str containing the url or IP of an http proxy host. If this is
      not specified, the ProxyConfig will be initialized without an HTTP proxy
      configured.
    http_port: An int port number for the HTTP proxy host.
    https_host: A str containing the url or IP of an https proxy host. If this
      is not specified, the ProxyConfig will be initialized without an HTTPS
      proxy configured.
    https_port: An int port number for the HTTPS proxy host.
    cafile: A str containing the path to a custom ca file.
    disable_certificate_validation: A boolean indicating whether or not to
      disable certificate validation.

  Returns:
    An initialized ProxyConfig using the given configurations.
  """
  http_proxy = None
  https_proxy = None

  if http_host:
    http_proxy = googleads.common.ProxyConfig.Proxy(http_host, http_port)

  if https_host:
    https_proxy = googleads.common.ProxyConfig.Proxy(https_host, https_port)

  return googleads.common.ProxyConfig(
      http_proxy, https_proxy, cafile=cafile,
      disable_certificate_validation=disable_certificate_validation)


class AdWordsHeaderHandlerTest(unittest.TestCase):
  """Tests for the googleads.adwords._AdWordsHeaderHandler class."""

  def setUp(self):
    self.report_downloader_headers = {}
    self.oauth2_client = mock.Mock()
    self.oauth_header = {'Authorization': 'header'}
    self.oauth2_client.CreateHttpHeader.return_value = self.oauth_header
    self.ccid = 'client customer id'
    self.dev_token = 'developer token'
    self.user_agent = 'user agent!'
    self.validate_only = True
    self.partial_failure = False
    self.enable_compression = False
    self.aw_client = GetAdWordsClient(
        ccid=self.ccid, dev_token=self.dev_token, user_agent=self.user_agent,
        oauth2_client=self.oauth2_client, validate_only=self.validate_only,
        partial_failure=self.partial_failure,
        report_downloader_headers=self.report_downloader_headers)
    self.header_handler = googleads.adwords._AdWordsHeaderHandler(
        self.aw_client, CURRENT_VERSION, self.enable_compression)

  def testSetHeaders(self):
    suds_client = mock.Mock()
    self.header_handler.SetHeaders(suds_client)
    # Check that the SOAP header has the correct values.
    suds_client.factory.create.assert_called_once_with(
        '{https://adwords.google.com/api/adwords/cm/%s}SoapHeader' %
        CURRENT_VERSION)
    soap_header = suds_client.factory.create.return_value
    self.assertEqual(self.ccid, soap_header.clientCustomerId)
    self.assertEqual(self.dev_token, soap_header.developerToken)
    self.assertEqual(
        ''.join([self.user_agent,
                 googleads.adwords._AdWordsHeaderHandler._LIB_SIG]),
        soap_header.userAgent)
    self.assertEqual(self.validate_only, soap_header.validateOnly)
    self.assertEqual(self.partial_failure, soap_header.partialFailure)
    # Check that the suds client has the correct values.
    suds_client.set_options.assert_any_call(
        soapheaders=soap_header, headers=self.oauth_header)

  def testGetReportDownloadHeadersOverrideDefaults(self):
    self.aw_client.report_downloader_headers = {
        'skip_report_header': True, 'skip_column_header': False,
        'skip_report_summary': False, 'use_raw_enum_values': True}
    expected_return_value = {
        'Content-type': 'application/x-www-form-urlencoded',
        'developerToken': self.dev_token,
        'clientCustomerId': self.ccid,
        'Authorization': 'header',
        'User-Agent': ''.join([
            self.user_agent, googleads.adwords._AdWordsHeaderHandler._LIB_SIG,
            ',gzip']),
        'skipReportHeader': 'False',
        'skipColumnHeader': 'True',
        'skipReportSummary': 'False',
        'useRawEnumValues': 'True'
    }
    self.assertEqual(expected_return_value,
                     self.header_handler.GetReportDownloadHeaders(
                         skip_report_header=False,
                         skip_column_header=True,
                         skip_report_summary=False,
                         use_raw_enum_values=True))

  def testGetReportDownloadHeadersWithDefaultsFromConfig(self):
    self.aw_client.report_download_headers = {
        'skip_report_header': True, 'skip_column_header': False,
        'skip_report_summary': False, 'use_raw_enum_values': True}
    expected_return_value = {
        'Content-type': 'application/x-www-form-urlencoded',
        'developerToken': self.dev_token,
        'clientCustomerId': self.ccid,
        'Authorization': 'header',
        'User-Agent': ''.join([
            self.user_agent, googleads.adwords._AdWordsHeaderHandler._LIB_SIG,
            ',gzip']),
        'skipReportHeader': 'True',
        'skipColumnHeader': 'False',
        'skipReportSummary': 'False',
        'useRawEnumValues': 'True'
    }
    self.assertEqual(expected_return_value,
                     self.header_handler.GetReportDownloadHeaders())

  def testGetReportDownloadHeadersWithInvalidKeyword(self):
    self.assertRaises(
        googleads.errors.GoogleAdsValueError,
        self.header_handler.GetReportDownloadHeaders, invalid_key_word=True)

  def testGetReportDownloadHeadersWithKeywordArguments(self):
    updated_ccid = 'updated client customer id'
    expected_return_value = {
        'Content-type': 'application/x-www-form-urlencoded',
        'developerToken': self.dev_token,
        'clientCustomerId': updated_ccid,
        'Authorization': 'header',
        'User-Agent': ''.join([
            self.user_agent, googleads.adwords._AdWordsHeaderHandler._LIB_SIG,
            ',gzip']),
        'skipReportHeader': 'True',
        'skipColumnHeader': 'True',
        'skipReportSummary': 'True',
        'includeZeroImpressions': 'True',
        'useRawEnumValues': 'True'
    }
    self.assertEqual(expected_return_value,
                     self.header_handler.GetReportDownloadHeaders(
                         skip_report_header=True,
                         skip_column_header=True,
                         skip_report_summary=True,
                         include_zero_impressions=True,
                         use_raw_enum_values=True,
                         client_customer_id=updated_ccid))

  def testGetReportDownloadHeadersWithNoOptionalHeaders(self):
    expected_return_value = {
        'Content-type': 'application/x-www-form-urlencoded',
        'developerToken': self.dev_token,
        'clientCustomerId': self.ccid,
        'Authorization': 'header',
        'User-Agent': ''.join([
            self.user_agent, googleads.adwords._AdWordsHeaderHandler._LIB_SIG,
            ',gzip'])
    }
    self.assertEqual(expected_return_value,
                     self.header_handler.GetReportDownloadHeaders())


class AdWordsClientTest(unittest.TestCase):
  """Tests for the googleads.adwords.AdWordsClient class."""

  def setUp(self):
    self.load_from_storage_path = os.path.join(
        os.path.dirname(__file__), 'test_data/adwords_googleads.yaml')
    self.https_proxy_host = 'myproxy'
    self.https_proxy_port = 443
    self.proxy_config = GetProxyConfig(https_host=self.https_proxy_host,
                                       https_port=self.https_proxy_port)
    self.file_cache = suds.cache.FileCache
    self.no_cache = suds.cache.NoCache()
    self.adwords_client = GetAdWordsClient()
    self.aw_client = GetAdWordsClient(
        proxy_config=self.proxy_config)
    self.header_handler = googleads.adwords._AdWordsHeaderHandler(
        self.adwords_client, CURRENT_VERSION, False)


  def testLoadFromStorage(self):
    with mock.patch('googleads.oauth2.GoogleRefreshTokenClient.Refresh'):
      self.assertIsInstance(googleads.adwords.AdWordsClient.LoadFromStorage(
          path=self.load_from_storage_path),
                            googleads.adwords.AdWordsClient)

  def testLoadFromStorageWithCompressionEnabled(self):
    enable_compression = True
    user_agent_gzip_template = '%s (gzip)'
    default_user_agent = 'unit testing'

    with mock.patch('googleads.common.LoadFromStorage') as mock_load:
      mock_load.return_value = {
          'developer_token': 'abcdEFghIjkLMOpqRs',
          'oauth2_client': mock.Mock(),
          'user_agent': default_user_agent,
          'enable_compression': enable_compression
      }
      client = googleads.adwords.AdWordsClient.LoadFromStorage()
      self.assertEqual(enable_compression, client.enable_compression)
      self.assertEqual(user_agent_gzip_template % default_user_agent,
                       client.user_agent)

  def testLoadFromStorageWithNonASCIIUserAgent(self):
    with mock.patch('googleads.common.LoadFromStorage') as mock_load:
      mock_load.return_value = {
          'developer_token': 'abcdEFghIjkLMOpqRs',
          'oauth2_client': mock.Mock(),
          'user_agent': u'ゼロ'
      }
      self.assertRaises(googleads.errors.GoogleAdsValueError,
                        googleads.adwords.AdWordsClient.LoadFromStorage)

  def testLoadFromStorageWithNoUserAgent(self):
    with mock.patch('googleads.common.LoadFromStorage') as mock_load:
      mock_load.return_value = {
          'developer_token': 'abcdEFghIjkLMOpqRs',
          'oauth2_client': mock.Mock()
      }

      client = googleads.adwords.AdWordsClient.LoadFromStorage()
      self.assertEquals(client.user_agent, 'unknown')

  def testGetService_success(self):
    service = googleads.adwords._SERVICE_MAP[CURRENT_VERSION].keys()[0]
    namespace = googleads.adwords._SERVICE_MAP[CURRENT_VERSION][service]
    # Use a custom server. Also test what happens if the server ends with a
    # trailing slash
    server = 'https://testing.test.com/'

    with mock.patch('googleads.common.LoggingMessagePlugin') as mock_plugin:
      with mock.patch('suds.client.Client') as mock_client:
        with mock.patch('googleads.common.ProxyConfig._SudsProxyTransport'
                       ) as mock_transport:
          mock_plugin.return_value = mock.Mock()
          mock_transport.return_value = mock.Mock()
          client = GetAdWordsClient()
          suds_service = client.GetService(
              service, CURRENT_VERSION, server)

          mock_client.assert_called_once_with(
              'https://testing.test.com/api/adwords/%s/%s/%s?wsdl'
              % (namespace, CURRENT_VERSION, service),
              transport=mock_transport.return_value, timeout=3600,
              plugins=[mock_plugin.return_value])
      self.assertIsInstance(suds_service, googleads.common.SudsServiceProxy)

  def testGetService_successWithFileCache(self):
    service = googleads.adwords._SERVICE_MAP[CURRENT_VERSION].keys()[0]
    namespace = googleads.adwords._SERVICE_MAP[CURRENT_VERSION][service]
    # Use a custom server. Also test what happens if the server ends with a
    # trailing slash
    server = 'https://testing.test.com/'

    with mock.patch('googleads.common.LoggingMessagePlugin') as mock_plugin:
      with mock.patch('suds.client.Client') as mock_client:
        with mock.patch('googleads.common.ProxyConfig._SudsProxyTransport'
                       ) as mock_transport:
          mock_plugin.return_value = mock.Mock()
          mock_transport.return_value = mock.Mock()
          client = GetAdWordsClient(cache=self.file_cache)
          suds_service = client.GetService(
              service, CURRENT_VERSION, server)

          mock_client.assert_called_once_with(
              'https://testing.test.com/api/adwords/%s/%s/%s?wsdl'
              % (namespace, CURRENT_VERSION, service),
              transport=mock_transport.return_value, timeout=3600,
              cache=self.file_cache, plugins=[mock_plugin.return_value])
      self.assertIsInstance(suds_service, googleads.common.SudsServiceProxy)

  def testGetService_successWithNoCache(self):
    service = googleads.adwords._SERVICE_MAP[CURRENT_VERSION].keys()[0]
    namespace = googleads.adwords._SERVICE_MAP[CURRENT_VERSION][service]
    # Use a custom server. Also test what happens if the server ends with a
    # trailing slash
    server = 'https://testing.test.com/'

    with mock.patch('googleads.common.LoggingMessagePlugin') as mock_plugin:
      with mock.patch('suds.client.Client') as mock_client:
        with mock.patch('googleads.common.ProxyConfig._SudsProxyTransport'
                       ) as mock_transport:
          mock_plugin.return_value = mock.Mock()
          mock_transport.return_value = mock.Mock()
          client = GetAdWordsClient(cache=self.no_cache)
          suds_service = client.GetService(
              service, CURRENT_VERSION, server)

          mock_client.assert_called_once_with(
              'https://testing.test.com/api/adwords/%s/%s/%s?wsdl'
              % (namespace, CURRENT_VERSION, service),
              transport=mock_transport.return_value, timeout=3600,
              cache=self.no_cache, plugins=[mock_plugin.return_value])
      self.assertIsInstance(suds_service, googleads.common.SudsServiceProxy)

  def testGetService_successWithoutProxy(self):
    service = googleads.adwords._SERVICE_MAP[CURRENT_VERSION].keys()[0]
    namespace = googleads.adwords._SERVICE_MAP[CURRENT_VERSION][service]

    # Use the default server without a proxy.
    with mock.patch('googleads.common.LoggingMessagePlugin') as mock_plugin:
      with mock.patch('suds.client.Client') as mock_client:
        with mock.patch('googleads.common.ProxyConfig._SudsProxyTransport'
                       ) as mock_transport:
          mock_transport.return_value = mock.Mock()
          client = GetAdWordsClient()
          suds_service = client.GetService(service, CURRENT_VERSION)

          mock_client.assert_called_once_with(
              'https://adwords.google.com/api/adwords/%s/%s/%s?wsdl'
              % (namespace, CURRENT_VERSION, service),
              transport=mock_transport.return_value, timeout=3600,
              plugins=[mock_plugin.return_value])
          self.assertFalse(mock_client.return_value.set_options.called)
          self.assertIsInstance(suds_service, googleads.common.SudsServiceProxy)

  def testGetService_badService(self):
    version = CURRENT_VERSION
    self.assertRaises(
        googleads.errors.GoogleAdsValueError,
        self.adwords_client.GetService,
        'GYIVyievfyiovslf', version)

  def testGetService_badVersion(self):
    self.assertRaises(
        googleads.errors.GoogleAdsValueError, self.adwords_client.GetService,
        'CampaignService', '11111')

  def testGetService_compressionEnabled(self):
    service = googleads.adwords._SERVICE_MAP[CURRENT_VERSION].keys()[0]
    client = GetAdWordsClient()
    client.enable_compression = True

    with mock.patch('suds.client.Client'):
      with mock.patch('googleads.adwords._AdWordsHeaderHandler') as mock_h:
        client.GetService(service, CURRENT_VERSION)
        mock_h.assert_called_once_with(client, CURRENT_VERSION,
                                       client.enable_compression)

  def testGetBatchJobHelper(self):
    with mock.patch('googleads.adwords.BatchJobHelper') as mock_helper:
      self.assertEqual(
          mock_helper.return_value,
          self.adwords_client.GetBatchJobHelper())

  def testGetReportDownloader(self):
    with mock.patch('googleads.adwords.ReportDownloader') as mock_downloader:
      self.assertEqual(
          mock_downloader.return_value,
          self.adwords_client.GetReportDownloader('version', 'server'))
      mock_downloader.assert_called_once_with(
          self.adwords_client, 'version', 'server')

  def testSetClientCustomerId(self):
    suds_client = mock.Mock()
    ccid = 'modified'
    # Check that the SOAP header has the modified client customer id.
    self.adwords_client.SetClientCustomerId(ccid)
    self.header_handler.SetHeaders(suds_client)
    soap_header = suds_client.factory.create.return_value
    self.assertEqual(ccid, soap_header.clientCustomerId)


class BatchJobHelperTest(unittest.TestCase):

  """Test suite for BatchJobHelper utility."""

  def setUp(self):
    """Prepare tests."""
    self.client = GetAdWordsClient()
    self.batch_job_helper = self.client.GetBatchJobHelper()

  def testGetId(self):
    expected = [-x for x in range(1, 101)]
    for value in expected:
      self.assertEqual(value, self.batch_job_helper.GetId())

  def testUploadOperations(self):
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    'BuildUploadRequest') as mock_build_request:
      mock_request = mock.Mock()
      mock_request.data = 'in disguise.'
      mock_build_request.return_value = mock_request
      with mock.patch('googleads.adwords.IncrementalUploadHelper'
                      '._InitializeURL') as mock_init:
        mock_init.return_value = 'https://www.google.com'
        with mock.patch('urllib2.OpenerDirector.open') as mock_open:
          self.batch_job_helper.UploadOperations([[]])
          mock_open.assert_called_with(mock_request)


class BatchJobUploadRequestBuilderTest(unittest.TestCase):

  """Test suite for the BatchJobUploadRequestBuilder."""

  ENVELOPE_NS = 'http://schemas.xmlsoap.org/soap/envelope/'

  def setUp(self):
    """Prepare tests."""
    self.client = GetAdWordsClient()
    self.request_builder = self.client.GetBatchJobHelper()._request_builder
    self.version = self.request_builder._version
    self.upload_url = 'https://goo.gl/IaQQsJ'
    self.sample_xml = ('<operations><id>!n3vERg0Nn4Run4r0und4NDd35Er7Y0u!~</id>'
                       '</operations>')
    sample_xml_length = len(self.sample_xml)
    self.complete_request_body = '%s%s%s' % (
        self.request_builder._UPLOAD_PREFIX_TEMPLATE % (
            self.request_builder._adwords_endpoint),
        self.sample_xml,
        self.request_builder._UPLOAD_SUFFIX)
    self.request_body_complete = '%s%s%s' % (
        self.request_builder._UPLOAD_PREFIX_TEMPLATE % (
            self.request_builder._adwords_endpoint),
        self.sample_xml,
        self.request_builder._UPLOAD_SUFFIX)
    self.request_body_start = '%s%s' % (
        self.request_builder._UPLOAD_PREFIX_TEMPLATE %
        self.request_builder._adwords_endpoint, self.sample_xml)
    self.request_body_end = '%s%s' % (
        self.sample_xml,
        self.request_builder._UPLOAD_SUFFIX)
    self.single_upload_headers = {
        'Content-type': 'application/xml',
        'Content-range': 'bytes %s-%s/%s' % (
            0,
            self.request_builder._BATCH_JOB_INCREMENT - 1,
            self.request_builder._BATCH_JOB_INCREMENT),
        'Content-length': self.request_builder._BATCH_JOB_INCREMENT
        }
    self.incremental_upload_headers = {
        'Content-type': 'application/xml',
        'Content-range': 'bytes %s-%s/*' % (
            self.request_builder._BATCH_JOB_INCREMENT,
            (self.request_builder._BATCH_JOB_INCREMENT * 2) - 1
        ),
        'Content-length': self.request_builder._BATCH_JOB_INCREMENT
    }

  @classmethod
  def setUpClass(cls):
    test_dir = os.path.dirname(__file__)
    with open(os.path.join(
        test_dir, 'test_data/batch_job_util_budget_template.txt')) as handler:
      cls.BUDGET_TEMPLATE = handler.read()
    with open(os.path.join(
        test_dir,
        'test_data/batch_job_util_campaign_criterion_template.txt')) as handler:
      cls.CAMPAIGN_CRITERION_TEMPLATE = handler.read()
    with open(os.path.join(
        test_dir,
        'test_data/batch_job_util_campaign_label_template.txt')) as handler:
      cls.CAMPAIGN_LABEL_TEMPLATE = handler.read()
    with open(os.path.join(
        test_dir, 'test_data/batch_job_util_invalid_request.txt')) as handler:
      cls.INVALID_API_REQUEST = handler.read()
    with open(os.path.join(
        test_dir, 'test_data/batch_job_util_not_request.txt')) as handler:
      cls.NOT_API_REQUEST = handler.read()
    with open(os.path.join(
        test_dir, 'test_data/batch_job_util_raw_request_template.txt')
             ) as handler:
      cls.RAW_API_REQUEST_TEMPLATE = handler.read()
    with open(os.path.join(
        test_dir, 'test_data/batch_job_util_operations_template.txt')
             ) as handler:
      cls.OPERATIONS_TEMPLATE = handler.read()
    with open(os.path.join(
        test_dir, 'test_data/batch_job_util_upload_template.txt')) as handler:
      cls.UPLOAD_OPERATIONS_TEMPLATE = handler.read()

  def ExpandOperandTemplate(self, operation_type, operand):
    """Expands the appropriate operand for the given operation_type.

    Args:
      operation_type: str indicating the type of operation the operand is being
        expanded for. Accepted types include: "BudgetOperation",
        "CampaignCriterionOperation", and "CampaignLabelOperation".
      operand: dict containing fields for the operation_type's operand.

    Returns:
      A str containing the expanded operand.

    Raises:
      ValueError: if an unsupported operation_type is specified.
    """
    if operation_type == 'BudgetOperation':
      return self.BUDGET_TEMPLATE % (
          operand['budgetId'], operand['name'],
          operand['amount']['microAmount'], operand['deliveryMethod'])
    elif operation_type == 'CampaignCriterionOperation':
      return self.CAMPAIGN_CRITERION_TEMPLATE % (
          operand['CampaignCriterion.Type'], operand['campaignId'],
          operand['criterion']['Criterion.Type'],
          operand['criterion']['text'],
          operand['criterion']['matchType'])
    elif operation_type == 'CampaignLabelOperation':
      return self.CAMPAIGN_LABEL_TEMPLATE % (
          operand['campaignId'], operand['labelId'])
    else:
      raise ValueError('Invalid operation_type "%s" specified.'
                       % operation_type)

  def GenerateOperations(self, operation_type, num_operations):
    """Generates a set of operations of the given type.

    Args:
      operation_type: str indicating the type of operation to be generated.
        Accepted types include: "BudgetOperation", "CampaignCriterionOperation",
        and "CampaignLabelOperation".
      num_operations: a positive int defining the number of operations to be
        generated.

    Returns:
      A tuple where the first item indicates the method to be used in the
      request and the second is a list of dictionaries containing distinct
      operations of the given operation_type.

    Raises:
      ValueError: if an unsupported operation_type is specified.
    """
    operation_range = range(1, num_operations + 1)

    if operation_type == 'BudgetOperation':
      return ('mutate', [{
          'operator': 'ADD',
          'xsi_type': 'BudgetOperation',
          'operand': {
              'budgetId': str(i),
              'name': 'Batch budget #%s' % i,
              'amount': {'microAmount': str(3333333 * i)},
              'deliveryMethod': 'STANDARD'}
      } for i in operation_range])
    elif operation_type == 'CampaignCriterionOperation':
      return ('mutate', [{
          'operator': 'ADD',
          'xsi_type': 'CampaignCriterionOperation',
          'operand': {
              'xsi_type': 'NegativeCampaignCriterion',
              'campaignId': str(100 * i),
              'criterion': {
                  'xsi_type': 'Keyword',
                  'text': 'venus %s' % i,
                  'matchType': 'BROAD'
              }
          }
      } for i in operation_range])
    elif operation_type == 'CampaignLabelOperation':
      return ('mutateLabel', [{
          'operator': 'ADD',
          'xsi_type': 'CampaignLabelOperation',
          'operand': {
              'campaignId': 123 * i,
              'labelId': 321 * i}
      } for i in operation_range])
    else:
      raise ValueError('Invalid operation_type "%s" specified.'
                       % operation_type)

  def GenerateValidRequest(self, operation_type, num_operations=1):
    """Generates a valid API request containing the given number of operations.

    Args:
      operation_type: str indicating the type of operation to be generated.
        Accepted types include: "BudgetOperation", "CampaignCriterionOperation",
        and "CampaignLabelOperation".
      num_operations: a positive int defining the number of operations to be
        generated.

    Returns:
      A tuple containing the operations used to construct str containing a valid
      API request.

    Raises:
      ValueError: if an unsupported operation_type is specified.
    """
    method, ops = self.GenerateOperations(operation_type, num_operations)

    ops_xml = ''.join([self.OPERATIONS_TEMPLATE % (
        op['operator'], op['xsi_type'],
        self.ExpandOperandTemplate(operation_type, op['operand'])
    ) for op in ops])

    request = self.RAW_API_REQUEST_TEMPLATE.decode('utf-8') % (
        self.version, self.version, method, ops_xml, method)

    return (ops, request)

  def GenerateValidUnicodeRequest(self, operations):
    """Generates a valid API request containing the given number of operations.

    Args:
      operations: a positive int defining the number of BudgetOperations to be
      generated.

    Returns:
      A tuple containing the operations used to construct unicode containing a
      valid API request.
    """
    ops = self.GenerateUnicodeBudgetOperations(operations)
    method = 'mutate'
    ops_xml = ''.join([self.OPERATIONS_TEMPLATE % (
        op['operator'], op['xsi_type'],
        self.ExpandOperandTemplate('BudgetOperation', op['operand'])
    ) for op in ops])

    request = (self.RAW_API_REQUEST_TEMPLATE % (
        self.version, self.version, method, ops_xml, method)).encode('utf-8')

    return (ops, request)

  def GenerateUnicodeBudgetOperations(self, operations):
    """Generates request containing given number of BudgetOperations.

    Args:
      operations: a positive int defining the number of BudgetOperations to be
        generated.
    Returns:
      A list of dictionaries containing distinct BudgetOperations.
    """
    return [{
        'operator': 'ADD',
        'xsi_type': 'BudgetOperation',
        'operand': {
            'budgetId': str(i),
            'name': u'アングリーバード Batch budget #%d' % i,
            'amount': {'microAmount': str(3333333 * i)},
            'deliveryMethod': 'STANDARD'}
    } for i in range(1, operations + 1)]

  def testGetPaddingLength(self):
    length = len(self.sample_xml)
    padding = self.request_builder._GetPaddingLength(length)
    self.assertTrue(
        padding == self.request_builder._BATCH_JOB_INCREMENT - length)

  def testExtractOperations(self):
    """Tests whether operations XML was extracted and formatted correctly.

    Verifies that the xsi_type has been properly assigned.
    """
    _, operations = self.GenerateOperations('CampaignCriterionOperation', 1)
    raw_xml = self.request_builder._GenerateRawRequestXML(operations)
    operations_xml = self.request_builder._ExtractOperations(raw_xml)
    # Put operations in a format that allows us to easily verify the behavior.
    ElementTree.register_namespace(
        'xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    # Need to declare xsi for ElementTree to parse operations properly.
    body = ElementTree.fromstring(
        '<body xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">%s'
        '</body>' % operations_xml)
    self.assertTrue(body.tag == 'body')
    ops_element = body.find('operations')
    # Check that the xsi_type has been set correctly.
    self.assertTrue(ops_element.attrib[
        '{http://www.w3.org/2001/XMLSchema-instance}type'] ==
                    'CampaignCriterionOperation')
    operand = ops_element.find('operand')
    self.assertTrue(operand.attrib[
        '{http://www.w3.org/2001/XMLSchema-instance}type'] ==
                    'NegativeCampaignCriterion')
    criterion = operand.find('criterion')
    self.assertTrue(criterion.attrib[
        '{http://www.w3.org/2001/XMLSchema-instance}type'] ==
                    'Keyword')

  def testFormatForBatchJobService(self):
    """Tests whether namespaces have been removed."""
    operations_amount = 5
    _, ops = self.GenerateOperations('CampaignCriterionOperation',
                                     operations_amount)
    root = ElementTree.fromstring(self.request_builder._GenerateRawRequestXML(
        ops))
    body = root.find('{%s}Body' % self.ENVELOPE_NS)
    mutate = body.find('{%s}mutate' % self.request_builder._adwords_endpoint)
    self.request_builder._FormatForBatchJobService(mutate)
    self.assertTrue(self.request_builder._adwords_endpoint not in mutate.tag)
    self.assertTrue(len(mutate) == operations_amount)

    for ops in mutate:
      self.assertTrue(self.request_builder._adwords_endpoint not in ops.tag)
      for child in ops:
        self.assertTrue(self.request_builder._adwords_endpoint not in
                        child.tag)
      operand = ops.find('operand')
      self.assertTrue(len(operand.attrib) == 1)
      self.assertTrue(
          'ns' not in
          operand.attrib['{http://www.w3.org/2001/XMLSchema-instance}type'])
      for child in operand:
        self.assertTrue(self.request_builder._adwords_endpoint not in
                        child.tag)
      criterion = operand.find('criterion')
      self.assertTrue(
          'ns' not in
          criterion.attrib['{http://www.w3.org/2001/XMLSchema-instance}type'])
      for child in criterion:
        self.assertTrue(self.request_builder._adwords_endpoint not in
                        child.tag)

  def testGenerateOperationsXMLNoXsiType(self):
    """Tests whether _GenerateOperationsXML raises ValueError if no xsi_type.
    """
    _, operations = self.GenerateOperations('CampaignCriterionOperation', 1)
    del operations[0]['xsi_type']
    self.assertRaises(
        googleads.errors.AdWordsBatchJobServiceInvalidOperationError,
        self.request_builder._GenerateOperationsXML, operations)

  def testGenerateOperationsXMLWithNoOperations(self):
    """Tests whether _GenerateOperationsXML produces empty str if no operations.
    """
    _, operations = self.GenerateOperations('CampaignCriterionOperation', 0)
    raw_xml = self.request_builder._GenerateOperationsXML(
        operations)
    self.assertTrue(raw_xml is '')

  def testGenerateRawRequestXMLFromBogusOperation(self):
    """Tests whether an invalid operation raises an Exception."""
    bogus_operations = [{
        'operator': 'ADD',
        'xsi_type': 'BogusOperation',
        'operand': {
            'bogusProperty': 'bogusValue'}
    }]

    self.assertRaises(KeyError,
                      self.request_builder._GenerateRawRequestXML,
                      bogus_operations)

  def testGenerateRawRequestXMLFromCampaignLabelOperation(self):
    """Tests whether raw request xml can be produced from a label operation."""
    ops = [{
        'operator': 'ADD',
        'xsi_type': 'CampaignLabelOperation',
        'operand': {'campaignId': 0, 'labelId': 0}
    }]

    root = ElementTree.fromstring(
        self.request_builder._GenerateRawRequestXML(ops))
    self.assertTrue(len(root) == 2)
    body = root.find('{%s}Body' % self.ENVELOPE_NS)
    self.assertTrue(len(body) == 1)
    mutate_label = body.find('{%s}mutateLabel'
                             % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate_label) == len(ops))

  def testGenerateRawRequestXMLFromSingleOperation(self):
    """Tests whether raw request xml can be produced from a single operation."""
    operations_amount = 1
    _, ops = self.GenerateOperations('BudgetOperation', operations_amount)

    root = ElementTree.fromstring(
        self.request_builder._GenerateRawRequestXML(ops))
    self.assertTrue(len(root) == 2)
    body = root.find('{%s}Body' % self.ENVELOPE_NS)
    self.assertTrue(len(body) == 1)
    mutate = body.find('{%s}mutate' % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate) == operations_amount)

    for i in range(0, operations_amount):
      operations = mutate[i]
      self.assertEqual(operations.tag, '{%s}operations' %
                       self.request_builder._adwords_endpoint)
      self.assertTrue(len(operations._children) == len(ops[i].keys()))
      self.assertEqual(operations.find(
          '{%s}operator' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operator'])
      self.assertEqual(
          operations.find(
              '{%s}Operation.Type' %
              self.request_builder._adwords_endpoint).text,
          ops[i]['xsi_type'])
      operand = operations.find(
          '{%s}operand' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operand._children) == len(ops[i]['operand'].keys()))
      self.assertEqual(operand.find(
          '{%s}budgetId' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['budgetId'])
      self.assertEqual(operand.find(
          '{%s}name' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['name'])
      amount = operand.find('{%s}amount' %
                            self.request_builder._adwords_endpoint)
      self.assertTrue(len(amount._children) ==
                      len(ops[i]['operand']['amount'].keys()))
      self.assertEqual(amount.find(
          '{%s}microAmount' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['amount']['microAmount'])
      self.assertEqual(operand.find(
          '{%s}deliveryMethod' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['deliveryMethod'])

  def testGenerateRawRequestXMLFromMultipleOperations(self):
    """Tests whether raw request xml can be produced for multiple operations."""
    operations_amount = 5
    _, ops = self.GenerateOperations('BudgetOperation', operations_amount)

    root = ElementTree.fromstring(
        self.request_builder._GenerateRawRequestXML(ops))
    self.assertTrue(len(root) == 2)
    body = root.find('{%s}Body' % self.ENVELOPE_NS)
    self.assertTrue(len(body) == 1)
    mutate = body.find('{%s}mutate' % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate) == operations_amount)

    for i in range(0, operations_amount):
      operations = mutate[i]
      self.assertEqual(
          operations.tag,
          '{%s}operations' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operations._children) == len(ops[i].keys()))
      self.assertEqual(operations.find(
          '{%s}operator' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operator'])
      self.assertEqual(operations.find(
          '{%s}Operation.Type' % self.request_builder._adwords_endpoint).text,
                       ops[i]['xsi_type'])
      operand = operations.find(
          '{%s}operand' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operand._children) == len(ops[i]['operand'].keys()))
      self.assertEqual(operand.find(
          '{%s}budgetId' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['budgetId'])
      self.assertEqual(operand.find(
          '{%s}name' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['name'])
      amount = operand.find(
          '{%s}amount' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(amount._children) ==
                      len(ops[i]['operand']['amount'].keys()))
      self.assertEqual(amount.find(
          '{%s}microAmount' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['amount']['microAmount'])
      self.assertEqual(operand.find(
          '{%s}deliveryMethod' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['deliveryMethod'])

  def testGenerateRawUnicodeRequestXMLFromSingleOperation(self):
    """Tests whether raw request xml can be produced from a single operation."""
    operations_amount = 1
    ops = self.GenerateUnicodeBudgetOperations(operations_amount)

    root = ElementTree.fromstring(
        self.request_builder._GenerateRawRequestXML(ops))
    self.assertTrue(len(root) == 2)
    body = root.find(u'{%s}Body' % self.ENVELOPE_NS)
    self.assertTrue(len(body) == 1)
    mutate = body.find(u'{%s}mutate' % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate) == operations_amount)

    for i in range(0, operations_amount):
      operations = mutate[i]
      self.assertEqual(operations.tag, '{%s}operations' %
                       self.request_builder._adwords_endpoint)
      self.assertTrue(len(operations._children) == len(ops[i].keys()))
      self.assertEqual(operations.find(
          '{%s}operator' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operator'])
      self.assertEqual(
          operations.find(
              '{%s}Operation.Type' %
              self.request_builder._adwords_endpoint).text,
          ops[i]['xsi_type'])
      operand = operations.find(
          '{%s}operand' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operand._children) == len(ops[i]['operand'].keys()))
      self.assertEqual(operand.find(
          '{%s}budgetId' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['budgetId'])
      self.assertEqual(operand.find(
          '{%s}name' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['name'])
      amount = operand.find('{%s}amount' %
                            self.request_builder._adwords_endpoint)
      self.assertTrue(len(amount._children) ==
                      len(ops[i]['operand']['amount'].keys()))
      self.assertEqual(amount.find(
          '{%s}microAmount' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['amount']['microAmount'])
      self.assertEqual(operand.find(
          '{%s}deliveryMethod' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['deliveryMethod'])

  def testGetRawOperationsFromValidSingleOperationMutateLabelRequest(self):
    """Test if operations XML can be retrieved for a single-op label request."""
    operations_amount = 1
    ops, request = self.GenerateValidRequest('CampaignLabelOperation',
                                             operations_amount)

    mutate = self.request_builder._GetRawOperationsFromXML(request)
    self.assertEqual(mutate.tag,
                     '{%s}mutateLabel' % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate._children) == operations_amount)

    for i in range(0, operations_amount):
      operations = mutate[i]
      self.assertEqual(
          operations.tag,
          '{%s}operations' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operations._children) == len(ops[i].keys()))
      self.assertEqual(operations.find(
          '{%s}operator' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operator'])
      self.assertEqual(operations.find(
          '{%s}Operation.Type' % self.request_builder._adwords_endpoint).text,
                       ops[i]['xsi_type'])
      operand = operations.find(
          '{%s}operand' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operand._children) == len(ops[i]['operand'].keys()))
      self.assertEqual(int(operand.find(
          '{%s}campaignId' % self.request_builder._adwords_endpoint).text),
                       ops[i]['operand']['campaignId'])
      self.assertEqual(int(operand.find(
          '{%s}labelId' % self.request_builder._adwords_endpoint).text),
                       ops[i]['operand']['labelId'])

  def testGetRawOperationsFromValidSingleOperationRequest(self):
    """Test if operations XML can be retrieved for a single-op request.

    Also verifies that the contents of generated XML are correct.
    """
    operations_amount = 1
    ops, request = self.GenerateValidRequest('BudgetOperation',
                                             operations_amount)

    mutate = self.request_builder._GetRawOperationsFromXML(request)
    self.assertEqual(mutate.tag,
                     '{%s}mutate' % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate._children) == operations_amount)

    for i in range(0, operations_amount):
      operations = mutate[i]
      self.assertEqual(
          operations.tag,
          '{%s}operations' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operations._children) == len(ops[i].keys()))
      self.assertEqual(operations.find(
          '{%s}operator' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operator'])
      self.assertEqual(operations.find(
          '{%s}Operation.Type' % self.request_builder._adwords_endpoint).text,
                       ops[i]['xsi_type'])
      operand = operations.find(
          '{%s}operand' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operand._children) == len(ops[i]['operand'].keys()))
      self.assertEqual(operand.find(
          '{%s}budgetId' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['budgetId'])
      self.assertEqual(operand.find(
          '{%s}name' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['name'])
      amount = operand.find(
          '{%s}amount' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(amount._children) ==
                      len(ops[i]['operand']['amount'].keys()))
      self.assertEqual(amount.find(
          '{%s}microAmount' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['amount']['microAmount'])
      self.assertEqual(operand.find(
          '{%s}deliveryMethod' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['deliveryMethod'])

  def testGetRawOperationsFromValidMultipleOperationRequest(self):
    """Test whether operations XML can be retrieved for a multi-op request.

    Also verifies that the contents of generated XML are correct.
    """
    operations_amount = 5
    ops, request = self.GenerateValidRequest('BudgetOperation',
                                             operations_amount)

    mutate = self.request_builder._GetRawOperationsFromXML(request)
    self.assertEqual(
        mutate.tag,
        '{%s}mutate' % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate._children) == operations_amount)

    for i in range(0, operations_amount):
      operations = mutate[i]
      self.assertEqual(
          operations.tag,
          '{%s}operations' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operations._children) == len(ops[i].keys()))
      self.assertEqual(operations.find(
          '{%s}operator' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operator'])
      self.assertEqual(operations.find(
          '{%s}Operation.Type' % self.request_builder._adwords_endpoint).text,
                       ops[i]['xsi_type'])
      operand = (operations.find(
          '{%s}operand' % self.request_builder._adwords_endpoint))
      self.assertTrue(len(operand._children) == len(ops[i]['operand'].keys()))
      self.assertEqual(operand.find(
          '{%s}budgetId' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['budgetId'])
      self.assertEqual(operand.find(
          '{%s}name' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['name'])
      amount = (operand.find(
          '{%s}amount' % self.request_builder._adwords_endpoint))
      self.assertTrue(len(amount._children) ==
                      len(ops[i]['operand']['amount'].keys()))
      self.assertEqual(amount.find(
          '{%s}microAmount' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['amount']['microAmount'])
      self.assertEqual(operand.find(
          '{%s}deliveryMethod' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['deliveryMethod'])

  def testGetRawOperationsFromValidMultipleOperationUnicodeRequest(self):
    """Test whether operations XML can be retrieved for a multi-op request.

    Also verifies that the contents of generated XML are correct.
    """
    operations_amount = 5
    ops, request = self.GenerateValidUnicodeRequest(operations_amount)

    mutate = self.request_builder._GetRawOperationsFromXML(request)
    self.assertEqual(
        mutate.tag,
        u'{%s}mutate' % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate._children) == operations_amount)

    for i in range(0, operations_amount):
      operations = mutate[i]
      self.assertEqual(
          operations.tag,
          '{%s}operations' % self.request_builder._adwords_endpoint)
      self.assertTrue(len(operations._children) == len(ops[i].keys()))
      self.assertEqual(operations.find(
          '{%s}operator' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operator'])
      self.assertEqual(operations.find(
          '{%s}Operation.Type' % self.request_builder._adwords_endpoint).text,
                       ops[i]['xsi_type'])
      operand = (operations.find(
          '{%s}operand' % self.request_builder._adwords_endpoint))
      self.assertTrue(len(operand._children) == len(ops[i]['operand'].keys()))
      self.assertEqual(operand.find(
          '{%s}budgetId' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['budgetId'])
      self.assertEqual(operand.find(
          '{%s}name' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['name'])
      amount = (operand.find(
          '{%s}amount' % self.request_builder._adwords_endpoint))
      self.assertTrue(len(amount._children) ==
                      len(ops[i]['operand']['amount'].keys()))
      self.assertEqual(amount.find(
          '{%s}microAmount' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['amount']['microAmount'])
      self.assertEqual(operand.find(
          '{%s}deliveryMethod' % self.request_builder._adwords_endpoint).text,
                       ops[i]['operand']['deliveryMethod'])

  def testGetRawOperationsFromValidZeroOperationRequest(self):
    """Test verifying empty request generated if no operations provided."""
    operations_amount = 0
    _, request = self.GenerateValidRequest('BudgetOperation',
                                           operations_amount)

    mutate = self.request_builder._GetRawOperationsFromXML(request)

    self.assertEqual(
        mutate.tag,
        '{%s}mutate' % self.request_builder._adwords_endpoint)
    self.assertTrue(len(mutate._children) == operations_amount)

  def testGetRawOperationsFromInvalidRequest(self):
    """Test whether an invalid API request raises an Exception."""
    self.assertRaises(AttributeError,
                      self.request_builder._GetRawOperationsFromXML,
                      self.INVALID_API_REQUEST)

  def testGetRawOperationsFromNotXMLRequest(self):
    """Test whether non-XML input raises an Exception."""
    self.assertRaises(ElementTree.ParseError,
                      self.request_builder._GetRawOperationsFromXML,
                      self.NOT_API_REQUEST)

  def testBuildRequestForSingleUpload(self):
    """Test whether a single upload request is build correctly."""
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    '_BuildUploadRequestBody') as mock_request_body_builder:
      mock_request_body_builder.return_value = self.sample_xml
      req = self.request_builder.BuildUploadRequest(self.upload_url, [[]],
                                                    is_last=True)
      self.assertEqual(req.headers, self.single_upload_headers)
      self.assertEqual(req.get_method(), 'PUT')

  def testBuildRequestForIncrementalUpload(self):
    """Test whether an incremental upload request is built correctly."""
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    '_BuildUploadRequestBody') as mock_request_body_builder:
      mock_request_body_builder.return_value = self.sample_xml
      req = self.request_builder.BuildUploadRequest(
          self.upload_url, [[]],
          current_content_length=self.request_builder._BATCH_JOB_INCREMENT)
      self.assertEqual(req.headers, self.incremental_upload_headers)
      self.assertEqual(req.get_method(), 'PUT')

  def testBuildUploadRequestBody(self):
    """Test whether a a complete request body is built correctly."""
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    '_GenerateOperationsXML') as mock_generate_xml:
      mock_generate_xml.return_value = self.sample_xml
      with mock.patch('googleads.adwords.BatchJobHelper._'
                      'SudsUploadRequestBuilder.'
                      '_GetPaddingLength') as mock_get_padding_length:
        mock_get_padding_length.return_value = 0
        increment = self.request_builder._BuildUploadRequestBody([[]])
        self.assertTrue(increment == self.request_body_complete)

  def testBuildUploadRequestBodyWithSuffix(self):
    """Test whether a request body is built correctly with only the suffix."""
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    '_GenerateOperationsXML') as mock_generate_xml:
      mock_generate_xml.return_value = self.sample_xml
      with mock.patch('googleads.adwords.BatchJobHelper.'
                      '_SudsUploadRequestBuilder.'
                      '_GetPaddingLength') as mock_get_padding_length:
        mock_get_padding_length.return_value = 0
        increment = self.request_builder._BuildUploadRequestBody(
            [[]], has_prefix=False)
        self.assertTrue(increment == self.request_body_end)

  def testBuildUploadRequestBodyWithoutPrefixOrSuffix(self):
    """Test whether a request body is built correctly without prefix/suffix."""
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    '_GenerateOperationsXML') as mock_generate_xml:
      mock_generate_xml.return_value = self.sample_xml
      with mock.patch('googleads.adwords.BatchJobHelper.'
                      '_SudsUploadRequestBuilder.'
                      '_GetPaddingLength') as mock_get_padding_length:
        mock_get_padding_length.return_value = 0
        increment = self.request_builder._BuildUploadRequestBody(
            [[]], has_prefix=False, has_suffix=False)
        self.assertTrue(increment == self.sample_xml)

  def testBuildUploadRequestBodyWithOnlyPrefix(self):
    """Test whether a request body is built correctly with only the prefix."""
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    '_GenerateOperationsXML') as mock_generate_xml:
      mock_generate_xml.return_value = self.sample_xml
      with mock.patch('googleads.adwords.BatchJobHelper.'
                      '_SudsUploadRequestBuilder.'
                      '_GetPaddingLength') as mock_get_padding_length:
        mock_get_padding_length.return_value = 0
        increment = self.request_builder._BuildUploadRequestBody(
            [[]], has_suffix=False)
        self.assertTrue(increment == self.request_body_start)


class IncrementalUploadHelperTest(unittest.TestCase):

  """Test suite for the IncrementalUploadHelper."""

  def setUp(self):
    """Prepare tests."""
    self.client = GetAdWordsClient()
    self.batch_job_helper = self.client.GetBatchJobHelper()
    self.version = self.batch_job_helper._version
    self.original_url = 'https://goo.gl/w8tkpK'
    self.initialized_url = 'https://goo.gl/Xtaq83'

    with mock.patch('urllib2.OpenerDirector.open') as mock_open:
      mock_open.return_value.headers = {
          'location': self.initialized_url
      }
      self.incremental_uploader = (
          self.batch_job_helper.GetIncrementalUploadHelper(
              self.original_url))

    self.incremental_uploader_dump = (
        '{current_content_length: 0, is_last: false, '
        'upload_url: \'https://goo.gl/Xtaq83\', version: %s}\n' % self.version)

  def testDump(self):
    expected = self.incremental_uploader_dump

    with tempfile.NamedTemporaryFile(delete=False, mode='w') as t:
      name = t.name
      self.incremental_uploader.Dump(t)

    with open(name, mode='r') as handler:
      dump_data = handler.read()

    self.assertEqual(expected, dump_data)

  def testLoad(self):
    s = StringIO.StringIO(self.incremental_uploader_dump)

    with mock.patch('urllib2.urlopen') as mock_open:
      mock_open.return_value.headers = {
          'location': self.initialized_url
      }
      with mock.patch('googleads.adwords.IncrementalUploadHelper'
                      '._InitializeURL') as mock_init:
        mock_init.return_value = self.initialized_url
        restored_uploader = googleads.adwords.IncrementalUploadHelper.Load(
            s, client=self.client)

    self.assertEquals(restored_uploader._current_content_length,
                      self.incremental_uploader._current_content_length)
    self.assertEquals(restored_uploader._is_last,
                      self.incremental_uploader._is_last)
    self.assertEquals(restored_uploader._request_builder._version,
                      self.version)
    self.assertEquals(restored_uploader._upload_url,
                      self.incremental_uploader._upload_url)

  def testUploadOperations(self):
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    'BuildUploadRequest') as mock_build_request:
      mock_request = mock.MagicMock()
      mock_build_request.return_value = mock_request
      with mock.patch('urllib2.OpenerDirector.open') as mock_open:
        self.incremental_uploader.UploadOperations([[]], True)
        mock_open.assert_called_with(mock_request)

  def testUploadOperationsAfterFinished(self):
    with mock.patch('googleads.adwords.BatchJobHelper.'
                    '_SudsUploadRequestBuilder.'
                    'BuildUploadRequest') as mock_build_request:
      mock_request = mock.MagicMock()
      mock_build_request.return_value = mock_request
      with mock.patch('urllib2.OpenerDirector.open'):
        self.incremental_uploader.UploadOperations([[]], True)
        self.assertRaises(
            googleads.errors.AdWordsBatchJobServiceInvalidOperationError,
            self.incremental_uploader.UploadOperations, {})


class ResponseParserTest(unittest.TestCase):
  """Test suite for the ResponseParser."""

  def setUp(self):
    """Prepare tests."""
    self.client = GetAdWordsClient()
    self.response_parser = googleads.adwords.BatchJobHelper.GetResponseParser()

  @classmethod
  def setUpClass(cls):
    test_dir = os.path.dirname(__file__)
    with open(os.path.join(
        test_dir, 'test_data/batch_job_util_response_template.txt')) as handler:
      cls.API_RESPONSE_XML_TEMPLATE = handler.read()

  def testParseResponse(self):
    campaign_id = '1'
    name = 'Test Campaign'
    status = 'PAUSED'
    serving_status = 'SUSPENDED'
    start_date = '20151116'
    end_date = '20371230'
    budget_id = '2'
    budget_name = 'Test Budget'
    micro_amount = '50000000'
    delivery_method = 'STANDARD'
    is_explicitly_shared = 'true'
    bidding_strategy_type = 'MANUAL_CPC'

    response = (
        self.response_parser.ParseResponse(
            self.API_RESPONSE_XML_TEMPLATE %
            (campaign_id, name, status, serving_status, start_date, end_date,
             budget_id, budget_name, micro_amount, delivery_method,
             is_explicitly_shared, bidding_strategy_type))
        ['mutateResponse']['rval'])

    # Assert that we correct parsed the response (2 results: Budget & Campaign)
    self.assertTrue(len(response) == 2)

    campaign = response[1]['result']['Campaign']
    self.assertTrue(campaign['id'] == campaign_id)
    self.assertTrue(campaign['name'] == name)
    self.assertTrue(campaign['status'] == status)
    self.assertTrue(campaign['servingStatus'] == serving_status)
    self.assertTrue(campaign['startDate'] == start_date)
    self.assertTrue(campaign['endDate'] == end_date)
    self.assertTrue(campaign['budget']['name'] == budget_name)
    self.assertTrue(campaign['budget']['amount']['microAmount'] == micro_amount)
    self.assertTrue(campaign['budget']['isExplicitlyShared'] ==
                    is_explicitly_shared)
    self.assertTrue(
        campaign['biddingStrategyConfiguration']['biddingStrategyType'] ==
        bidding_strategy_type)

  def testParseUnicodeResponse(self):
    campaign_id = u'1'
    name = u'アングリーバード'
    status = u'PAUSED'
    serving_status = u'SUSPENDED'
    start_date = u'20151116'
    end_date = u'20371230'
    budget_id = u'2'
    budget_name = u'Test Budget'
    micro_amount = u'50000000'
    delivery_method = u'STANDARD'
    is_explicitly_shared = u'true'
    bidding_strategy_type = u'MANUAL_CPC'

    response = (
        self.response_parser.ParseResponse(
            self.API_RESPONSE_XML_TEMPLATE %
            (campaign_id, name, status, serving_status, start_date, end_date,
             budget_id, budget_name, micro_amount, delivery_method,
             is_explicitly_shared, bidding_strategy_type))
        ['mutateResponse']['rval'])

    self.assertTrue(len(response) == 2)
    campaign = response[1]['result']['Campaign']
    self.assertTrue(campaign['name'] == name)


class ReportDownloaderTest(unittest.TestCase):
  """Tests for the googleads.adwords.ReportDownloader class."""

  def setUp(self):
    self.version = CURRENT_VERSION
    self.marshaller = mock.Mock()
    self.header_handler = mock.Mock()
    self.adwords_client = mock.Mock()
    self.adwords_client.proxy_config = GetProxyConfig()
    self.opener = mock.Mock()

    with mock.patch('suds.client.Client'):
      with mock.patch('suds.xsd.doctor'):
        with mock.patch('suds.mx.literal.Literal') as mock_literal:
          with mock.patch(
              'googleads.adwords._AdWordsHeaderHandler') as mock_handler:
            with mock.patch(
                URL_REQUEST_PATH + '.OpenerDirector') as mock_opener:
              mock_literal.return_value = self.marshaller
              mock_handler.return_value = self.header_handler
              mock_opener.return_value = self.opener
              self.report_downloader = googleads.adwords.ReportDownloader(
                  self.adwords_client, self.version)

  def testDownloadReport(self):
    output_file = io.StringIO()
    report_definition = {'table': 'campaigns',
                         'downloadFormat': 'CSV'}
    serialized_report = 'nuinbwuign'
    post_body = urllib.urlencode({'__rdxml': serialized_report})
    if not PYTHON2:
      post_body = bytes(post_body, 'utf-8')
    headers = {'Authorization': 'ya29.something'}
    self.header_handler.GetReportDownloadHeaders.return_value = headers
    content = u'CONTENT STRING 广告客户'
    fake_request = io.StringIO() if PYTHON2 else io.BytesIO()
    fake_request.write(content if PYTHON2 else bytes(content, 'utf-8'))
    fake_request.seek(0)
    self.marshaller.process.return_value = serialized_report

    with mock.patch('suds.mx.Content') as mock_content:
      with mock.patch(URL_REQUEST_PATH + '.Request') as mock_request:
        self.opener.open.return_value = fake_request
        self.report_downloader.DownloadReport(report_definition, output_file,
                                              skip_report_header=True,
                                              use_raw_enum_values=False)
        mock_request.assert_called_once_with(
            ('https://adwords.google.com/api/adwords/reportdownload/%s'
             % self.version), post_body, headers)
        self.opener.open.assert_called_once_with(mock_request.return_value)
        self.marshaller.process.assert_called_once_with(
            mock_content.return_value)
        self.assertEqual(content, output_file.getvalue())
        self.header_handler.GetReportDownloadHeaders.assert_called_once_with(
            skip_report_header=True, use_raw_enum_values=False)

  def testDownloadReportAsString(self):
    report_definition = {'table': 'campaigns',
                         'downloadFormat': 'CSV'}
    serialized_report = 'nuinbwuign'
    post_body = urllib.urlencode({'__rdxml': serialized_report})
    if not PYTHON2:
      post_body = bytes(post_body, 'utf-8')
    headers = {'Authorization': 'ya29.something'}
    self.header_handler.GetReportDownloadHeaders.return_value = headers
    content = u'CONTENT STRING アングリーバード'
    fake_request = io.BytesIO()
    fake_request.write(content.encode('utf-8') if PYTHON2
                       else bytes(content, 'utf-8'))
    fake_request.seek(0)
    self.marshaller.process.return_value = serialized_report

    with mock.patch('suds.mx.Content') as mock_content:
      with mock.patch(URL_REQUEST_PATH + '.Request') as mock_request:
        self.opener.open.return_value = fake_request
        s = self.report_downloader.DownloadReportAsString(report_definition)
        mock_request.assert_called_once_with(
            ('https://adwords.google.com/api/adwords/reportdownload/%s'
             % self.version), post_body, headers)
        self.opener.open.assert_called_once_with(mock_request.return_value)
        self.marshaller.process.assert_called_once_with(
            mock_content.return_value)
        self.assertEqual(content, s)
        self.header_handler.GetReportDownloadHeaders.assert_called_once_with()

  def testDownloadReportAsStringWithAwql(self):
    query = 'SELECT Id FROM Campaign WHERE NAME LIKE \'%Test%\''
    file_format = 'CSV'
    post_body = urllib.urlencode({'__fmt': file_format, '__rdquery': query})
    if not PYTHON2:
      post_body = bytes(post_body, 'utf-8')
    headers = {'Authorization': 'ya29.something'}
    self.header_handler.GetReportDownloadHeaders.return_value = headers
    content = u'CONTENT STRING アングリーバード'
    fake_request = io.BytesIO()
    fake_request.write(content.encode('utf-8') if PYTHON2
                       else bytes(content, 'utf-8'))
    fake_request.seek(0)
    with mock.patch(URL_REQUEST_PATH + '.Request') as mock_request:
      self.opener.open.return_value = fake_request
      s = self.report_downloader.DownloadReportAsStringWithAwql(
          query, file_format, include_zero_impressions=True,
          use_raw_enum_values=False)
      mock_request.assert_called_once_with(
          ('https://adwords.google.com/api/adwords/reportdownload/%s'
           % self.version), post_body, headers)
      self.opener.open.assert_called_once_with(mock_request.return_value)
    self.assertEqual(content, s)
    self.header_handler.GetReportDownloadHeaders.assert_called_once_with(
        include_zero_impressions=True, use_raw_enum_values=False)

  def testDownloadReportCheckFormat_CSVStringSuccess(self):
    output_file = io.StringIO()

    try:
      self.report_downloader._DownloadReportCheckFormat('CSV', output_file)
    except googleads.errors.GoogleAdsValueError:
      self.fail('_DownloadReportCheckFormat raised GoogleAdsValueError'
                'unexpectedly!')

  def testDownloadReportCheckFormat_GZIPPEDBinaryFileSuccess(self):
    output_file = io.StringIO()

    try:
      self.report_downloader._DownloadReportCheckFormat('CSV', output_file)
    except googleads.errors.GoogleAdsValueError:
      self.fail('_DownloadReportCheckFormat raised GoogleAdsValueError'
                'unexpectedly!')

  def testDownloadReportCheckFormat_GZIPPEDBytesIOSuccess(self):
    output_file = tempfile.TemporaryFile(mode='wb')

    try:
      self.report_downloader._DownloadReportCheckFormat('GZIPPED_CSV',
                                                        output_file)
    except googleads.errors.GoogleAdsValueError:
      self.fail('_DownloadReportCheckFormat raised GoogleAdsValueError'
                'unexpectedly!')

  def testDownloadReportCheckFormat_GZIPPEDStringFailure(self):
    output_file = io.StringIO()

    self.assertRaises(googleads.errors.GoogleAdsValueError,
                      self.report_downloader._DownloadReportCheckFormat,
                      'GZIPPED_CSV', output_file)

  def testDownloadReportCheckFormat_Issue152(self):
    output_file = io.StringIO()
    output_file.mode = 'w+b'  # Verify writing and reading works.

    try:
      self.report_downloader._DownloadReportCheckFormat(
          'GZIPPED_CSV', output_file)
    except googleads.errors.GoogleAdsValueError:
      self.fail('_DownloadReportCheckFormat raised GoogleAdsValueError'
                'unexpectedly!')

    output_file.mode = 'r+b'  # Verify reading and writing works.

    try:
      self.report_downloader._DownloadReportCheckFormat(
          'GZIPPED_CSV', output_file)
    except googleads.errors.GoogleAdsValueError:
      self.fail('_DownloadReportCheckFormat raised GoogleAdsValueError'
                'unexpectedly!')

  def testDownloadReport_failure(self):
    output_file = io.StringIO()
    report_definition = {'table': 'campaigns',
                         'downloadFormat': 'CSV'}
    serialized_report = 'hjuibnibguo'
    post_body = urllib.urlencode({'__rdxml': serialized_report})
    if not PYTHON2:
      post_body = bytes(post_body, 'utf-8')
    headers = {'Authorization': 'ya29.something'}
    self.header_handler.GetReportDownloadHeaders.return_value = headers
    content = u'Page not found. :-('
    fake_request = io.StringIO() if PYTHON2 else io.BytesIO()
    fake_request.write(content if PYTHON2 else bytes(content, 'utf-8'))
    fake_request.seek(0)
    error = urllib2.HTTPError('', 400, 'Bad Request', {}, fp=fake_request)

    self.marshaller.process.return_value = serialized_report

    with mock.patch('suds.mx.Content') as mock_content:
      with mock.patch(URL_REQUEST_PATH + '.Request') as mock_request:
        self.opener.open.side_effect = error
        self.assertRaises(
            googleads.errors.AdWordsReportError,
            self.report_downloader.DownloadReport, report_definition,
            output_file)

        mock_request.assert_called_once_with(
            ('https://adwords.google.com/api/adwords/reportdownload/%s'
             % self.version), post_body, headers)
        self.opener.open.assert_called_once_with(mock_request.return_value)
        self.marshaller.process.assert_called_once_with(
            mock_content.return_value)
        self.assertEqual('', output_file.getvalue())
        self.header_handler.GetReportDownloadHeaders.assert_called_once_with()

  def testDownloadReportWithAwql(self):
    output_file = io.StringIO()
    query = 'SELECT Id FROM Campaign WHERE NAME LIKE \'%Test%\''
    file_format = 'CSV'
    post_body = urllib.urlencode({'__fmt': file_format, '__rdquery': query})
    if not PYTHON2:
      post_body = bytes(post_body, 'utf-8')
    headers = {'Authorization': 'ya29.something'}
    self.header_handler.GetReportDownloadHeaders.return_value = headers
    content = u'CONTENT STRING 广告客户'
    fake_request = io.StringIO() if PYTHON2 else io.BytesIO()
    fake_request.write(content if PYTHON2 else bytes(content, 'utf-8'))
    fake_request.seek(0)

    with mock.patch(URL_REQUEST_PATH + '.Request') as mock_request:
      self.opener.open.return_value = fake_request
      self.report_downloader.DownloadReportWithAwql(
          query, file_format, output_file)

      mock_request.assert_called_once_with(
          ('https://adwords.google.com/api/adwords/reportdownload/%s'
           % self.version), post_body, headers)
      self.opener.open.assert_called_once_with(mock_request.return_value)

    self.assertEqual(content, output_file.getvalue())
    self.header_handler.GetReportDownloadHeaders.assert_called_once_with()

  def testDownloadReportWithBytesIO(self):
    output_file = io.BytesIO()
    report_definition = {'table': 'campaigns',
                         'downloadFormat': 'GZIPPED_CSV'}
    serialized_report = 'nuinbwuign'
    post_body = urllib.urlencode({'__rdxml': serialized_report})
    if not PYTHON2:
      post_body = bytes(post_body, 'utf-8')
    headers = {'Authorization': 'ya29.something'}
    self.header_handler.GetReportDownloadHeaders.return_value = headers
    content = u'CONTENT STRING 广告客户'
    fake_request = io.BytesIO()
    fake_request.write(content.encode('utf-8') if PYTHON2
                       else bytes(content, 'utf-8'))
    fake_request.seek(0)
    self.marshaller.process.return_value = serialized_report

    with mock.patch('suds.mx.Content') as mock_content:
      with mock.patch(URL_REQUEST_PATH + '.Request') as mock_request:
        self.opener.open.return_value = fake_request
        self.report_downloader.DownloadReport(report_definition, output_file)
        mock_request.assert_called_once_with(
            ('https://adwords.google.com/api/adwords/reportdownload/%s'
             % self.version), post_body, headers)
        self.opener.open.assert_called_once_with(mock_request.return_value)
        self.marshaller.process.assert_called_once_with(
            mock_content.return_value)
        self.assertEqual(content, output_file.getvalue().decode('utf-8'))
        self.header_handler.GetReportDownloadHeaders.assert_called_once_with()

  def testExtractError_badRequest(self):
    response = mock.Mock()
    response.code = 400
    type_ = 'ReportDownloadError.INVALID_REPORT_DEFINITION_XML'
    trigger = 'Invalid enumeration.'
    field_path = 'Criteria.Type'
    content_template = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<reportDownloadError><ApiError><type>%s</type><trigger>%s</trigger>'
        '<fieldPath>%s</fieldPath></ApiError></reportDownloadError>')
    content = content_template % (type_, trigger, field_path)
    response.read.return_value = (content if PYTHON2
                                  else bytes(content, 'utf-8'))

    rval = self.report_downloader._ExtractError(response)
    self.assertEqual(type_, rval.type)
    self.assertEqual(trigger, rval.trigger)
    self.assertEqual(field_path, rval.field_path)
    self.assertEqual(response.code, rval.code)
    self.assertEqual(response, rval.error)
    self.assertEqual(content, rval.content)
    self.assertIsInstance(rval, googleads.errors.AdWordsReportBadRequestError)

    # Check that if the XML fields are empty, this still functions.
    content = content_template % ('', '', '')
    response.read.return_value = (content if PYTHON2
                                  else bytes(content, 'utf-8'))
    rval = self.report_downloader._ExtractError(response)
    self.assertEqual(None, rval.type)
    self.assertEqual(None, rval.trigger)
    self.assertEqual(None, rval.field_path)

  def testExtractError_malformedBadRequest(self):
    response = mock.Mock()
    response.code = 400
    content = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<reportDownloadError><ApiError><type>1234</type><trigger>5678'
               '</trigger></ApiError></ExtraElement></reportDownloadError>')
    response.read.return_value = (content if PYTHON2
                                  else bytes(content, 'utf-8'))

    rval = self.report_downloader._ExtractError(response)
    self.assertEqual(response.code, rval.code)
    self.assertEqual(response, rval.error)
    self.assertEqual(content, rval.content)
    self.assertIsInstance(rval, googleads.errors.AdWordsReportError)

  def testExtractError_notBadRequest(self):
    response = mock.Mock()
    response.code = 400
    content = 'Page not found!'
    response.read.return_value = (content if PYTHON2
                                  else bytes(content, 'utf-8'))

    rval = self.report_downloader._ExtractError(response)
    self.assertEqual(response.code, rval.code)
    self.assertEqual(response, rval.error)
    self.assertEqual(content, rval.content)
    self.assertIsInstance(rval, googleads.errors.AdWordsReportError)


if __name__ == '__main__':
  unittest.main()
