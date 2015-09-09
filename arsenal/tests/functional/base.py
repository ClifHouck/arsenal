# Copyright 2015 Rackspace
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import ConfigParser
import json
import math
import os
import random
import subprocess
import time

from oslotest import base
import requests


class TestCase(base.BaseTestCase):
    """Base test class for all functional tests."""

    def setUp(self):
        """Set the endpoints for ironic and glance.
        Create a config file for arsenal with default values
        set in the `set_config_values` method.
        """
        super(TestCase, self).setUp()
        self.processes_to_kill = []
        self.flavors = 3
        self.port = str(random.randint(2000, 9000))
        self.mimic_endpoint = "http://localhost"
        self.mimic_ironic_url = "{0}:{1}/ironic/v1/nodes".format(
            self.mimic_endpoint,
            self.port)
        self.mimic_glance_url = "{0}:{1}/glance/v2/images".format(
            self.mimic_endpoint,
            self.port)
        self.default_config_file = 'test_default' + self.port + '.conf'
        self.strategy = None
        self.generated_test_files = []

    def tearDown(self):
        """Kill arsenal and mimic processes
        """
        super(TestCase, self).tearDown()

        for each in self.processes_to_kill:
            try:
                each.kill()
            except OSError as e:
                if not ('No such process' in str(e)):
                    raise

        # Remove files generated by testing.
        for filename in self.generated_test_files:
            os.remove(filename)
        self.generated_test_files = []

    def start_mimic_service(self):
        """Start the mimic service and wait for the service to be started.
        """
        pid_filename = 'twistd{}.pid'.format(self.port)
        p = subprocess.Popen(['twistd', '-n',
                              '--pidfile={}'.format(pid_filename),
                              'mimic', '-l', self.port],
                             stdout=subprocess.PIPE)
        self.generated_test_files.append(pid_filename)
        self.processes_to_kill.append(p)
        while True:
            line = p.stdout.readline()
            if ((line == '' and p.poll() is not None) or  # process done
                    "Starting factory <twisted.web.server.Site instance"
                    in line):
                break

    def start_arsenal_service(self, config_file=None,
                              service_status="Started Arsenal service"):
        """Start the arsenal service with the given config file.
        If a config file is not provided, create and the use the default
        config file.
        """
        if not config_file:
            config_file = self.default_config_file
            config_values = self.set_config_values()
            self.create_arsenal_config_file(config_values,
                                            file_name=self.default_config_file)
        a = subprocess.Popen(['arsenal-director', '--config-file', config_file,
                              '-v'],
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.processes_to_kill.append(a)
        while True:
            line = a.stdout.readline()
            if ((line == '' and a.poll() is not None) or  # process done
                    service_status in line):
                break

    def generate_config_file_name(self, name='test'):
        """Create a config file name appending the port to it
        """
        return name + str(self.port) + '.conf'

    def set_config_values(self, dry_run=False, interval=1, rate_limit=100,
                          percentage_to_cache=0.5, image_weights=None,
                          default_image_weight=1):
        """Set values for the arsenal config file."""
        mimic_endpoint = self.mimic_endpoint
        port = self.port
        image_weights = (image_weights or
                         {'OnMetal - CentOS 6': 80,
                          'OnMetal - CentOS 7': 80,
                          'OnMetal - CoreOS (Alpha)': 11,
                          'OnMetal - CoreOS (Beta)': 1,
                          'OnMetal - CoreOS (Stable)': 5,
                          'OnMetal - Debian 7 (Wheezy)': 60,
                          'OnMetal - Debian 8 (Jessie)': 14,
                          'OnMetal - Debian Testing (Stretch)': 2,
                          'OnMetal - Debian Unstable (Sid)': 2,
                          'OnMetal - Fedora 21': 1,
                          'OnMetal - Fedora 22': 2,
                          'OnMetal - Ubuntu 12.04 LTS (Precise Pangolin)': 132,
                          'OnMetal - Ubuntu 14.04 LTS (Trusty Tahr)': 163,
                          'OnMetal - Ubuntu 15.04 (Vivid Vervet)': 3})
        return {
            'director':
                {'scout': 'onmetal_scout.OnMetalScout',
                 'dry_run': dry_run,
                 'poll_spacing': interval,
                 'directive_spacing': interval,
                 'cache_directive_rate_limit': rate_limit,
                 'cache_directive_limiting_period': interval,
                 'eject_directive_rate_limit': rate_limit,
                 'eject_directive_limiting_period': interval,
                 'log_statistics': True},
            'client_wrapper':
                {'call_max_retries': 3,
                 'call_retry_interval': 3,
                 'os_tenant_name': 232323,
                 'os_username': 'test-user',
                 'region_name': 'ORD',
                 'service_name': 'cloudServersOpenStack',
                 'auth_system': 'rackspace',
                 'os_api_url': '{0}:{1}/identity/v2.0'.format(
                     mimic_endpoint, port),
                 'os_password': 'test-password'},
            'nova': {},
            'ironic':
                {'admin_username': 'test-admin',
                 'admin_password': 'test-admin-password',
                 'admin_tenant_name': 99999,
                 'admin_url': '{0}:{1}/identity/v2.0'.format(
                     mimic_endpoint, port),
                 'api_endpoint': '{0}:{1}/ironic/v1'.format(
                     mimic_endpoint, port)},
            'glance':
                {'api_endpoint': '{0}:{1}/glance/v2'.format(
                    mimic_endpoint, port),
                 'admin_auth_token': 'any-token-works'},
            'simple_proportional_strategy':
                {'percentage_to_cache': percentage_to_cache},
            'strategy':
                {'module_class': self.strategy or
                 'simple_proportional_strategy.SimpleProportionalStrategy',
                 'image_weights': image_weights,
                 'default_image_weight': default_image_weight}
        }

    def create_arsenal_config_file(self, config_values,
                                   file_name='test.conf'):
        """Given `config_values` object set the values in the
        arsensal.conf file.
        """
        config = ConfigParser.RawConfigParser()
        for each_key in config_values.keys():
            if not config.has_section(each_key):
                config.add_section(each_key)
            for key, value in config_values[each_key].iteritems():
                config.set(each_key, key, value)
        f = open(file_name, 'w')
        config.write(f)
        f.close()

        self.generated_test_files.append(file_name)

    def get_all_ironic_nodes(self):
        """Get a list of ironic nodes with details.
        """
        nodes_list_response = requests.get(self.mimic_ironic_url + '/detail')
        self.assertEqual(nodes_list_response.status_code, 200)
        ironic_nodes_list = nodes_list_response.json()['nodes']
        return ironic_nodes_list

    def get_provisioned_ironic_nodes(self):
        """Get a list of provisioned ironic nodes.
        """
        all_nodes = self.get_all_ironic_nodes()
        return [node for node in all_nodes
                if node.get('instance_uuid')]

    def get_unprovisioned_ironic_nodes(self):
        """Get a list of unprovisioned ironic nodes.
        """
        all_nodes = self.get_all_ironic_nodes()
        return [node for node in all_nodes
                if not node.get('instance_uuid')]

    def get_cached_unprovisioned_ironic_nodes(self):
        """Get the cached unprovioned nodes from the list of nodes in ironic.
        """
        all_nodes = self.get_all_ironic_nodes()
        return [node for node in all_nodes
                if ((node['driver_info'].get('cache_image_id')) and
                    (not node.get('instance_uuid')))]

    def get_uncached_unprovisioned_ironic_nodes(self):
        """Get the cached unprovioned nodes from the list of nodes in ironic.
        """
        all_nodes = self.get_all_ironic_nodes()
        return [node for node in all_nodes
                if ((not node['driver_info'].get('cache_image_id')) and
                    (not node.get('instance_uuid')))]

    def get_cached_ironic_nodes(self):
        """Get the cached nodes from the list of nodes in ironic.
        """
        all_nodes = self.get_all_ironic_nodes()
        return [node for node in all_nodes
                if (node['driver_info'].get('cache_image_id'))]

    def get_uncached_ironic_nodes(self):
        """Get the uncached nodes from the list of nodes in ironic.
        """
        all_nodes = self.get_all_ironic_nodes()
        return [node for node in all_nodes
                if not (node['driver_info'].get('cache_image_id'))]

    def get_cached_ironic_nodes_by_flavor(self):
        """Get the cached nodes from the list of nodes in ironic.
        If `filter_by_flavor` is `True` return a map of each flavor to
        cached ironic nodes of that flavor.
        """
        all_nodes = self.get_all_ironic_nodes()
        cache_node_by_flavor = {'onmetal-compute1': [], 'onmetal-io1': [],
                                'onmetal-memory1': []}
        for node in all_nodes:
            if (
                (node['driver_info'].get('cache_image_id')) and
                (node['extra'].get('flavor') in cache_node_by_flavor.keys())
            ):
                cache_node_by_flavor[node['extra']['flavor']].append(node)
        return cache_node_by_flavor

    def wait_for_cached_ironic_nodes(self, count, interval_time=1, timeout=5):
        """Wait for the number of cached ironic nodes."""
        end_time = time.time() + timeout
        while time.time() < end_time:
            cached_nodes = self.get_cached_ironic_nodes()
            if len(cached_nodes) == count:
                break
            time.sleep(interval_time)
        else:
            self.fail("Expected cached nodes count {0}, but got {1}".format(
                count, len(cached_nodes)))

    def wait_for_successful_recache(self, interval_time=1, timeout=5):
        """Waits for current images to be re-cached when the images
        are added or deleted.
        """
        end_time = time.time() + timeout
        while time.time() < end_time:
            cached_nodes = self.get_cached_ironic_nodes()
            nodes_per_image = self.list_ironic_nodes_by_image(
                cached_nodes,
                count=True)
            images = self.get_onmetal_images_names_from_mimic()
            if sorted(images) == sorted(nodes_per_image.keys()):
                break
            time.sleep(interval_time)
        else:
            self.fail("Expected {0} to be cached, got {1}".format(
                sorted(images),
                sorted(nodes_per_image.keys())))

    def calculate_percentage_to_be_cached(self, total_nodes, percentage,
                                          by_flavor=True):
        """Calulates the nodes to be cached given the percentage and the
        total_nodes.
        """
        if by_flavor:
            return (math.floor((total_nodes / self.flavors) *
                               percentage) * self.flavors)
        return (math.floor(total_nodes * percentage))

    def get_image_id_to_name_map_from_mimic(self):
        """Get a list of images and map the image id to name.
        Returns a dict object mapping the image id to image name
        """
        image_list_response = requests.get(self.mimic_glance_url)
        self.assertEqual(image_list_response.status_code, 200)
        return {each["id"]: each["name"]
                for each in image_list_response.json()['images']}

    def list_ironic_nodes_by_image(self, node_list, count=False):
        """Given a list of nodes, map the nodes of the same image and
        return list of nodes per image.
        If `count` is `True` return the count of nodes per image.
        """
        image_map = self.get_image_id_to_name_map_from_mimic()
        nodes_per_image = {}
        for node in node_list:
            image_name = image_map.get(node['driver_info']['cache_image_id'])
            if nodes_per_image.get(image_name):
                nodes_per_image[image_name].append(node['uuid'])
            else:
                nodes_per_image[image_name] = [node['uuid']]
        if count:
            nodes_per_image_count = {}
            for key, value in nodes_per_image.iteritems():
                if key:
                    nodes_per_image_count[key] = len(value)
            return nodes_per_image_count
        return nodes_per_image

    def add_new_nodes_to_mimic(self, num=1, memory_mb=131072):
        """Add the `num` number of nodes in mimic.
        By default adds onmetal-io1 flavors.
        """
        request_json = json.dumps({'properties': {'memory_mb': memory_mb}})
        for _ in range(num):
            resp = requests.post(self.mimic_ironic_url, data=request_json)
            self.assertEqual(resp.status_code, 201)

    def delete_node_on_mimic(self, node_id):
        """Delete the specified node_id from mimic."""
        try:
            resp = requests.delete(self.mimic_ironic_url + '/' + node_id)
            self.assertEqual(resp.status_code, 204)
        except Exception:
            self.fail("Delete node failed with {0}.".format(resp.status_code))

    def delete_cached_nodes_on_mimic(self, num=1, cached=True):
        """Deletes the `num` number of cached or uncached nodes in mimic."""
        if cached:
            node_list = self.get_cached_ironic_nodes()
        else:
            node_list = self.get_uncached_ironic_nodes()
        if not (num <= len(node_list)):
            self.fail("Cant delete more nodes than that exist!")
        node_ids_list = [each['uuid'] for each in node_list]
        for node_id in node_ids_list[:int(num)]:
            self.delete_node_on_mimic(node_id)

    def delete_image_from_mimic(self, images):
        """Delete given onmetal images from Mimic."""
        for each in images:
            resp = requests.delete(self.mimic_glance_url + '/' + each)
            self.assertEqual(resp.status_code, 204)

    def get_onmetal_images_names_from_mimic(self):
        """Returns list of onmetal images names in mimic."""
        image_list_response = requests.get(self.mimic_glance_url)
        self.assertEqual(image_list_response.status_code, 200)
        return [image['name'] for image in image_list_response.json()['images']
                if image['name'].startswith('OnMetal')]

    def get_onmetal_images_ids_from_mimic(self):
        """Returns list of onmetal images ids in mimic."""
        image_list_response = requests.get(self.mimic_glance_url)
        self.assertEqual(image_list_response.status_code, 200)
        return [image['id'] for image in image_list_response.json()['images']
                if image['name'].startswith('OnMetal')]

    def add_new_image_to_mimic(self, images):
        """Adds new onmetal images to Mimic."""
        for image in images:
            resp = requests.post(self.mimic_glance_url, data=json.dumps(image))
            self.assertEqual(resp.status_code, 201)

    def set_provision_state(self, node_list, provision_state):
        """Set the provision state to all the nodes in `node_list`."""
        for node in node_list:
            url = self.mimic_ironic_url + '/' + node + '/states/provision'
            resp = requests.put(url,
                                data=json.dumps({"target": provision_state}))
            self.assertEqual(resp.status_code, 202)