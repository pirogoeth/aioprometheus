''' This module implements a Prometheus metrics binary formatter.

Protocol Buffers is used as the data serialisation format.
'''

import pyrobuf_util

from .base import IFormatter
from ..collectors import Counter, Gauge, Summary, Histogram

import prometheus_metrics_proto as pmp


class BinaryFormatter(IFormatter):
    ''' This formatter encodes into the Protocol Buffers binary format '''

    def __init__(self, timestamp=False):
        '''
        :param timestamp: a boolean flag that when True will add a timestamp
          to metric.
        '''
        self.timestamp = timestamp
        self._headers = {
            'Content-Type': "application/vnd.google.protobuf; "
                            "proto=io.prometheus.client.MetricFamily; "
                            "encoding=delimited"}

    def get_headers(self):
        return self._headers

    def _create_labels(self, labels):
        ''' Return a list of LabelPair objects for each label. '''
        return [
            pmp.LabelPair(name=k, value=str(v)) for k, v in labels.items()]

    def _format_counter(self, counter, name, const_labels):
        '''
        :param counter: a 2-tuple containing labels and the counter value.
        :param labels: a dict of labels for a metric.
        :param const_labels: a dict of constant labels to be associated with
          the metric.
        '''
        counter_labels, counter_value = counter
        labels = self._unify_labels(counter_labels, const_labels, ordered=True)
        pb_labels = self._create_labels(labels)

        pb_counter = pmp.Counter(value=counter_value)

        pb_metric = pmp.Metric(label=pb_labels, counter=pb_counter)
        if self.timestamp:
            pb_metric.timestamp_ms = self._get_timestamp()

        return pb_metric

    def _format_gauge(self, gauge, name, const_labels):
        '''
        :param gauge: a 2-tuple containing labels and the gauge value.
        :param labels: a dict of labels for a metric.
        :param const_labels: a dict of constant labels to be associated with
          the metric.
        '''
        gauge_labels, gauge_value = gauge
        labels = self._unify_labels(gauge_labels, const_labels, ordered=True)
        pb_labels = self._create_labels(labels)

        pb_gauge = pmp.Gauge(value=gauge_value)

        pb_metric = pmp.Metric(label=pb_labels, gauge=pb_gauge)
        if self.timestamp:
            pb_metric.timestamp_ms = self._get_timestamp()
        return pb_metric

    def _format_summary(self, summary, name, const_labels):
        '''
        :param summary: a 2-tuple containing labels and a dict representing
          the summary value. The dict contains keys for each quantile as
          well as the sum and count fields.
        :param labels: a dict of labels for a metric.
        :param const_labels: a dict of constant labels to be associated with
          the metric.
        '''
        summary_labels, summary_value_dict = summary
        labels = self._unify_labels(summary_labels, const_labels, ordered=True)
        pb_labels = self._create_labels(labels)

        pb_quantiles = []
        for k, v in summary_value_dict.items():
            if not isinstance(k, str):
                pb_quantile = pmp.Quantile(quantile=k, value=v)
                pb_quantiles.append(pb_quantile)

        pb_summary = pmp.Summary(
            sample_count=summary_value_dict['count'],
            sample_sum=summary_value_dict['sum'],
            quantile=pb_quantiles)

        pb_metric = pmp.Metric(label=pb_labels, summary=pb_summary)
        if self.timestamp:
            pb_metric.timestamp_ms = self._get_timestamp()

        return pb_metric

    def _format_histogram(self, histogram, name, const_labels):
        '''
        :param histogram: a 2-tuple containing labels and a dict representing
          the histogram value. The dict contains keys for each bucket as
          well as the sum and count fields.
        :param labels: a dict of labels for a metric.
        :param const_labels: a dict of constant labels to be associated with
          the metric.
        '''
        histogram_labels, histogram_value_dict = histogram
        labels = self._unify_labels(
            histogram_labels, const_labels, ordered=True)
        pb_labels = self._create_labels(labels)

        pb_buckets = []
        for k, v in histogram_value_dict.items():
            if not isinstance(k, str):
                pb_bucket = pmp.Bucket(cumulative_count=v, upper_bound=k)
                pb_buckets.append(pb_bucket)

        pb_histogram = pmp.Histogram(
            sample_count=histogram_value_dict['count'],
            sample_sum=histogram_value_dict['sum'],
            bucket=pb_buckets)

        pb_metric = pmp.Metric(label=pb_labels, histogram=pb_histogram)
        if self.timestamp:
            pb_metric.timestamp_ms = self._get_timestamp()

        return pb_metric

    def marshall_collector(self, collector):
        '''
        :return: a :class:`MetricFamily` object
        '''

        if isinstance(collector, Counter):
            metric_type = pmp.COUNTER
            exec_method = self._format_counter
        elif isinstance(collector, Gauge):
            metric_type = pmp.GAUGE
            exec_method = self._format_gauge
        elif isinstance(collector, Summary):
            metric_type = pmp.SUMMARY
            exec_method = self._format_summary
        elif isinstance(collector, Histogram):
            metric_type = pmp.HISTOGRAM
            exec_method = self._format_histogram
        else:
            raise TypeError("Not a valid object format")

        pb_metrics = []

        for i in collector.get_all():
            r = exec_method(i, collector.name, collector.const_labels)
            pb_metrics.append(r)

        pb_metric_family = pmp.MetricFamily(
            name=collector.name, help=collector.doc,
            type=metric_type, metric=pb_metrics)

        return pb_metric_family

    def marshall(self, registry):
        ''' Marshall the collectors in the registry into binary protocol
        buffer format.

        The Prometheus metrics parser expects each metric (MetricFamily) to
        be prefixed with a varint containing the size of the encoded metric.

        :returns: bytes
        '''
        payload = []
        for i in registry.get_all():
            encoded_metric = self.marshall_collector(i).SerializeToString()
            length = pyrobuf_util.to_varint(len(encoded_metric))
            payload.append(length + encoded_metric)
        return b"".join(payload)
