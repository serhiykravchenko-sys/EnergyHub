import json
import unittest
from pathlib import Path


def charts(node):
    if isinstance(node,dict):
        if node.get('type') in {'custom:apexcharts-card','custom:button-card'}:
            yield node
        for value in node.values():
            yield from charts(value)
    elif isinstance(node,list):
        for value in node:
            yield from charts(value)


class ForecastChartTests(unittest.TestCase):
    def test_separate_forecast_chart_preserves_existing_balance_chart(self):
        root=Path(__file__).resolve().parents[2]
        data=json.loads((root/'homeassistant/live/storage/lovelace.dashboard_powmr1').read_text(encoding='utf-8'))
        rows=list(charts(data))
        self.assertEqual(1,sum(c.get('header',{}).get('title')=='Consumption, EV Potential & Grid — 7 days' for c in rows))
        chart=next(c for c in rows if c.get('header',{}).get('title')=='Solar forecast — 5 days')
        self.assertEqual('custom:apexcharts-card',chart['type'])
        resources=json.loads((root/'homeassistant/live/storage/lovelace_resources').read_text(encoding='utf-8'))
        self.assertTrue(any('apexcharts-card.js' in r['url'] for r in resources['data']['items']))
        self.assertEqual('5d',chart['graph_span'])
        axis=chart['apex_config']['xaxis']
        self.assertEqual('numeric',axis['type'])
        self.assertEqual(10,axis['tickAmount'])
        self.assertFalse(axis['labels']['hideOverlappingLabels'])
        solar,consumption=chart['series']
        self.assertEqual(('column','#f39c12'),(solar['type'],solar['color']))
        self.assertEqual(('line','#3498db'),(consumption['type'],consumption['color']))
        self.assertIn('consumption_samples',consumption['data_generator'])
        self.assertIn('return []',consumption['data_generator'])
        for series in (solar,consumption):
            self.assertIn('today.getTime()+43200000+i*86400000',series['data_generator'])
