#!/usr/bin/python
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

DOCUMENTATION = '''
---
module: docdb_instance
short_description: Manages individual DocumentDB clusterinstances
description:
    - Manages individual DocumentDB cluster instances
options:
  availability_zone:
    description:
      - Availability zone in which to launch the instance.
      - Used when state=present.
      - When not specified, a random system-chosen AZ will be used.
    required: false
    default: null
  cluster_id:
    description:
      - Identifier of a cluster the instance will belong to.
      - Used when state=present and instance does not exist.
    required: false
    default: null
  engine:
    description:
      - Database engine to use
      - Used when state=present and instance does not exist.
    choices:
        - docdb
    required: false
    default: docdb
  instance_id:
    description:
      - Identifier of a DB instance
    required: false
  instance_type:
    description:
      - The instance type of the database.
      - Required when state=present.
    required: false
    default: null
  preferred_maintenance_window:
    description:
      - Maintenance window in format of ddd:hh24:mi-ddd:hh24:mi.  (Example: Mon:22:00-Mon:23:15)
      - Used when state=present.
      - If not specified then a random maintenance window is assigned.
    required: false
    default: null
  state:
    description:
      - "present" to create an instance, "absent" to delete an instance
    choices:
      - present
      - absent
    default: present
    required: false
  tags:
    description:
      - Dictionary of tags to apply to a resource.
      - Used when state=present.
    required: false
    default: null
  wait:
    description:
      - Whether or not to wait for instance to become available.
      - Used when state=present.
    choices:
        - yes
        - no
    required: false
    default: false
  wait_timeout:
    description:
      - How long to wait for instance to become available, when wait=yes
      - Defaults to 20 minutes.
      - Used when state=present and wait=yes.
    required: false
    default: 1200

author: "Sidnei Weber (@sidneiweber)"
extends_documentation_fragment:
    - aws
    - ec2
'''

EXAMPLES = '''
# Basic instance creation
- local_action:
    module: docdb_instance
    instance_id: my-new-instance
    instance_type: db.t2.small
    cluster_id: my-docdb-cluster
    tags:
      Name: my-new-instance
    state: present
'''

try:
    import boto3
    import botocore.exceptions
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False

import time

def terminate_db_instance(module, client, **params):
    try:
        check_instance = client.describe_db_instances(DBInstanceIdentifier=params['instance_id'])
        if 'DBInstances' in check_instance and len(check_instance['DBInstances']) == 1:
            delete_args = dict()
            result = client.delete_db_instance(DBInstanceIdentifier=params['instance_id'], **delete_args)
            # Nova alternativa de wait
            waiter = client.get_waiter('db_instance_deleted')
            waiter.wait(DBInstanceIdentifier=params['instance_id'])

    except botocore.exceptions.ClientError as e:
        result = True
        pass
    module.exit_json(result=result)

def create_db_instance(module, client, **params):

    api_args = dict()

    if params['instance_type'] is not None:
        api_args['DBInstanceClass'] = params['instance_type']
    if params['availability_zone'] is not None:
        api_args['AvailabilityZone'] = params['availability_zone']
    if params['preferred_maintenance_window'] is not None:
        api_args['PreferredMaintenanceWindow'] = params['preferred_maintenance_window']

    tags = None
    if params['tags'] is not None:
        tags = [{'Key': k, 'Value': v} for k, v in params['tags'].items()]

    try:
        check_instance = client.describe_db_instances(DBInstanceIdentifier=params['instance_id'])

        if 'DBInstances' not in check_instance or len(check_instance['DBInstances']) != 1:
            module.fail_json(msg='Failed to retrieve details for existing database instance')

        # Determine instance modifications to make
        instance = check_instance['DBInstances'][0]
        modify_args = dict()

        if modify_args:
            # Modify existing instance
            result = client.modify_db_instance(DBInstanceIdentifier=params['instance_id'], **modify_args)
        else:
            # Return existing instance details verbatim
            result = dict(DBInstance=instance)

        # Set instance tags
        tags_result = client.list_tags_for_resource(ResourceName=check_instance['DBInstances'][0]['DBInstanceArn'])
        if 'TagList' in tags_result:
            client.remove_tags_from_resource(ResourceName=check_instance['DBInstances'][0]['DBInstanceArn'], TagKeys=[t['Key'] for t in tags_result['TagList']])
            if tags is not None:
                api_args['Tags'] = tags
                client.add_tags_to_resource(ResourceName=check_instance['DBInstances'][0]['DBInstanceArn'], Tags=tags)

    except botocore.exceptions.ClientError as e:
        if e.response['Error']['Code'] == 'DBInstanceNotFound':
            api_args['DBInstanceIdentifier'] = params['instance_id']

            if params['cluster_id'] is not None:
                api_args['DBClusterIdentifier'] = params['cluster_id']
            if params['engine'] is not None:
                api_args['Engine'] = params['engine']
            if tags is not None:
                api_args['Tags'] = tags

            try:
                result = client.create_db_instance(**api_args)
            except (botocore.exceptions.ClientError, boto.exception.BotoServerError) as e:
                module.fail_json(msg=str(e), api_args=api_args)

        else:
            module.fail_json(msg=str(e), api_args=api_args)

    except boto.exception.BotoServerError as e:
        module.fail_json(msg=str(e), api_args=api_args)

    if params['wait']:
        wait_timeout = time.time() + params['wait_timeout']
        ready = False
        while not ready and wait_timeout > time.time():
            try:
                check_instance = client.describe_db_instances(DBInstanceIdentifier=params['instance_id'])
                if 'DBInstances' in check_instance and len(check_instance['DBInstances']) == 1:
                    if check_instance['DBInstances'][0]['DBInstanceStatus'].lower() == 'available':
                        ready = True

            except (botocore.exceptions.ClientError, boto.exception.BotoServerError) as e:
                pass

            if not ready:
                time.sleep(5)

        if wait_timeout <= time.time():
            if 'DBInstances' in check_instance and len(check_instance['DBInstances']) == 1:
                instance = check_instance['DBInstances'][0]
            else:
                instance = None
            module.fail_json(msg='Timed out waiting for DB instance to become available', instance=instance)

    module.exit_json(result=result)


def main():
    module_args = dict(
        availability_zone = dict(required=False, default=None),
        cluster_id = dict(required=False),
        engine = dict(required=False, choices=['docdb'], default='docdb'),
        final_db_snapshot_identifier=dict(required=False),
        instance_id = dict(required=True),
        instance_type = dict(required=False),
        preferred_maintenance_window = dict(required=False, default=None),
        state = dict(required=False, default='present', choices=['present', 'absent']),
        tags = dict(required=False, type='dict', default={}),
        wait = dict(required=False, type='bool', default=False),
        wait_timeout = dict(required=False, type='int', default=1200),
    )
    argument_spec = ec2_argument_spec()
    argument_spec.update(module_args)
    module = AnsibleModule(argument_spec=argument_spec)

    args_dict = {arg: module.params.get(arg) for arg in module_args.keys()}
    #module.fail_json(msg='test', args_dict=args_dict)

    if not HAS_BOTO3:
        module.fail_json(msg='boto3 required for this module')

    try:
        region, ec2_url, aws_connect_kwargs = get_aws_connection_info(module, boto3=True)
        docdb = boto3_conn(module, conn_type='client', resource='docdb', region=region, endpoint=ec2_url, **aws_connect_kwargs)

    except botocore.exceptions.ClientError as e:
        module.fail_json(msg="Boto3 Client Error - " + str(e))

    if module.params.get('state') == 'present':
        create_db_instance(module, docdb, **args_dict)
    elif module.params.get('state') == 'absent':
        terminate_db_instance(module, docdb, **args_dict)

# import module snippets
from ansible.module_utils.basic import *
from ansible.module_utils.ec2 import *

if __name__ == '__main__':
    main()
