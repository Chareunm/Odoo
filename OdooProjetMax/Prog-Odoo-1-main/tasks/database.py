# -*- coding: utf-8 -*-
# Copyright 2018 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).
from __future__ import print_function

import getpass
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime

import gnupg
import psycopg2
import requests
from invoke import task

from .common import (
    cd,
    cookiecutter_context,
    exit_msg,
    get_from_lastpass,
    gpg_decrypt_to_file,
    make_dir,
)

LPASS_GPG_DUMP_KEY_ID = 5794282849981145008
base_s3_dump_path = "s3://odoo-dumps"


@contextmanager
def ensure_db_container_up(ctx):
    """ Ensure the DB container is up and running.

    :param ctx:
    :return: True if already up, False if it wasn't
    """
    try:
        ctx.run('docker-compose port db 5432', hide=True)
        started = True
    except Exception:
        ctx.run('docker-compose up -d db', hide=True)
        running = False
        # Wait for the container to start
        count = 0
        while not running:
            try:
                ctx.run('docker-compose port db 5432', hide=True)
                running = True
            except Exception as e:
                count += 1
                # Raise the error after 3 failed attempts
                if count >= 3:
                    raise e
                print('Waiting for DB container to start')
                time.sleep(0.3)
        started = False
    yield
    # Stop the container if it wasn't already up and running
    if not started:
        ctx.run('docker-compose stop db', hide=True)


def get_db_container_port(ctx):
    """Get and return DB container port"""
    run_res = ctx.run('docker-compose port db 5432', hide=True)
    return str(int(run_res.stdout.split(':')[-1]))


def get_db_request_result(ctx, dbname, sql):
    """Return the execution of given SQL request on given db"""
    result = False
    with ensure_db_container_up(ctx):
        db_port = get_db_container_port(ctx)
        dsn = "host=localhost dbname=%s " "user=odoo password=odoo port=%s" % (
            dbname,
            db_port,
        )
        # Connect and list DBs
        with psycopg2.connect(dsn) as db_connection:
            with db_connection.cursor() as db_cursor:
                db_cursor.execute(sql)
                result = db_cursor.fetchall()
    return result


def get_db_list(ctx):
    """Return the list of db on container"""
    sql = """
        SELECT datname
        FROM pg_database
        WHERE datistemplate = false
        AND datname not in ('postgres', 'odoo');
    """
    databases_fetch = get_db_request_result(ctx, 'postgres', sql) or []
    return [db_name_tuple[0] for db_name_tuple in databases_fetch]


def expand_path(path):
    if path.startswith('~'):
        path = os.path.expanduser(path)
    return path


@task(name='list-versions')
def list_versions(ctx):
    """Print a table of DBs with Marabunta version and install date."""
    res = {}
    sql = """
        SELECT date_done, number
        FROM marabunta_version
        ORDER BY date_done DESC
        LIMIT 1;
    """
    # Get version for each DB
    db_list = get_db_list(ctx)
    for db_name in db_list:
        try:
            version_fetch = get_db_request_result(ctx, db_name, sql)
            version_tuple = version_fetch[0]
        except psycopg2.ProgrammingError:
            # Error expected when marabunta_version table does not exist
            version_tuple = (None, 'unknown')
        res[db_name] = version_tuple

    size1 = max([len(x) for x in res.keys()]) + 1
    size2 = max([len(x[1]) for x in res.values()]) + 1
    size3 = 10  # len('2018-01-01')
    cols = (('DB Name', size1), ('Version', size2), ('Install date', size3))
    thead = ''
    line_width = 4  # spaces
    for col_name, col_size in cols:
        thead += "{:<{size}}".format(col_name, size=col_size + 1)
        line_width += col_size
    print(thead)
    print('=' * line_width)
    for db_name, version in sorted(
        res.items(), key=lambda x: x[1][0] or datetime.min, reverse=True
    ):
        if version[0]:
            time = version[0].strftime('%Y-%m-%d')
        else:
            time = 'unknown'
        print(
            "{:<{size1}} {:<{size2}} {:<12}".format(
                db_name, version[1], time, size1=size1, size2=size2
            )
        )


@task(name='download-dump')
def download_dump(ctx, database_name, dumpdir='.'):
    """Download Dump

    Works only with Aws

    :param database_name: Aws database folder name like -> fighting_snail_1024
    :param dumpdir: Location of Dump directory
    :return: Decrypted Dump on the dumpdir
    """
    # TODO May be change the input (now it's database_name) given in hard but
    # after may be doing dict in Lastpass with {project_name: database_name}
    # or a other solution
    # TODO  to be able to select a dump which is not the latest one,
    # although the latest should obviously be default.

    # Get name of dump in aws list of dump
    try:
        dump_path = _get_list_of_dumps(ctx, database_name)[-1]  # get the last
    except IndexError:
        exit_msg('Dump not found for {}'.format(database_name))
    # gpg_fname is like fighting_snail_1024[...].pg.gpg
    gpg_fname = os.path.basename(dump_path)
    # fname is like fighting_snail_1024[...].pg
    fname = os.path.splitext(gpg_fname)[0]

    make_dir(dumpdir)
    with cd(dumpdir):
        s3_path_dump = os.path.join(
            base_s3_dump_path, database_name, gpg_fname
        )
        downloaded = False
        if not os.path.isfile(gpg_fname):
            print('S3 Downloading dump...')
            print('From:', s3_path_dump)
            print('to:', os.getcwd())
            _download_from_dumpbag(ctx, s3_path_dump)
            downloaded = True
        else:
            print(
                "A file named {} already exists, "
                "skipping download.".format(gpg_fname)
            )
        # decrypt again if does not exists or downloaded again
        if not os.path.isfile(fname) or downloaded:
            # TODO extract this part so it can be reused
            password_gpg = get_from_lastpass(ctx, LPASS_GPG_DUMP_KEY_ID, "-p")
            print("Decrypting with gpg")
            gpg_decrypt_to_file(ctx, password_gpg, gpg_fname)
            print("File decrypted as {}".format(fname))
        else:
            print(
                "A decrypted file named {} already exists, "
                "skipping decryption.".format(fname)
            )


@task(name='local-dump')
def local_dump(ctx, db_name='odoodb', path='.'):
    """Create a PG Dump for given database name.

    :param db_name: Name of the Database to dump
    :param path: Local path to store the dump
    :return: Dump file path
    """
    path = expand_path(path)
    with ensure_db_container_up(ctx):
        db_port = get_db_container_port(ctx)
        username = getpass.getuser()
        project_name = cookiecutter_context()['project_name']
        dump_name = '{}_{}-{}.pg'.format(
            username, project_name, datetime.now().strftime('%Y%m%d-%H%M%S')
        )
        dump_file_path = '{}/{}'.format(path, dump_name)
        ctx.run(
            'pg_dump -h localhost -p {} --format=c -U odoo --file {} {}'.format(
                db_port, dump_file_path, db_name
            ),
            hide=True,
        )
        print('Dump succesfully generated at %s' % dump_file_path)
    return dump_file_path


def encrypt_for_dump_bags(ctx, dump_file_path):
    """Encrypt dump to GPG using keys from dump-bag.odoo.camptocamp.ch

    :param dump_file_path: Path of *.pg dump file
    :return: Path of the encrypted GPG dump
    """
    gpg_file_path = '%s.gpg' % dump_file_path
    r = requests.get('https://dump-bag.odoo.camptocamp.ch/keys')
    gpg = gnupg.GPG()
    gpg.import_keys(r.text)
    fingerprints = [str(rec['fingerprint']) for rec in gpg.list_keys()]
    with open(dump_file_path, 'rb') as dump_file:
        data = gpg.encrypt(dump_file, *fingerprints)
    with open(gpg_file_path, 'wb') as encrypted_dump:
        encrypted_dump.write(data.data)
    print('Dump successfully encrypted at %s' % gpg_file_path)
    return gpg_file_path


@task(name='share-on-dumps-bag')
def share_on_dumps_bag(ctx, dump_file_path):
    """Encrypt and push a dump to Odoo Dump bags manually.

    GPG dump will be pushed to url s3://odoo-dumps/your_username

    :param dump_file_path: Path of *.pg dump file
    """
    dump_file_path = expand_path(dump_file_path)
    gpg_file_path = encrypt_for_dump_bags(ctx, dump_file_path)
    username = getpass.getuser()
    s3_dump_path = 's3://odoo-dumps/{}/{}'.format(
        username, os.path.basename(gpg_file_path)
    )
    ctx.run(
        'aws --profile=odoo-dumps s3 cp {} {}'.format(
            gpg_file_path, s3_dump_path
        ),
        hide=True,
    )
    # Set ShortExpire tag for the dump to be auto deleted after 1 week
    ctx.run(
        'aws --profile=odoo-dumps s3api put-object-tagging '
        '--bucket odoo-dumps --key %s/%s '
        '--tagging="TagSet=[{Key=ShortExpire,Value=True}]"'
        % (username, s3_dump_path),
        hide=True,
    )
    print('Encrypted dump successfully shared on dumps bag at:', s3_dump_path)
    print('NOTE: this dump will be auto-deleted after 7 days.')


@task(name='dump-and-share')
def dump_and_share(
    ctx, db_name='odoodb', tmp_path='/tmp', keep_local_dump=False
):
    """Create a dump and share it on Odoo Dumps Bag.

    Usage : invoke database.dump-and-share --db-name=mydb

    :param db_name: Name of the Database to dump
    :param tmp_path: Temporary local path to store the dump
    :param keep_local_dump: Boolean to keep the generated and encrypted dumps
    locally
    """
    tmp_path = expand_path(tmp_path)
    dump_file_path = local_dump(ctx, db_name=db_name, path=tmp_path)
    share_on_dumps_bag(ctx, dump_file_path)
    if not keep_local_dump:
        ctx.run('rm %s' % dump_file_path)
        ctx.run('rm %s.gpg' % dump_file_path)


@task(name='empty-my-dump-bag')
def empty_my_dump_bag(ctx):
    """Empty the content of s3://odoo-dumps/your_username.

    Please call this function as soon as your recipient did download your dump.
    """
    username = getpass.getuser()
    ctx.run(
        'aws --profile=odoo-dumps s3 rm s3://odoo-dumps/%s/ --recursive'
        % username,
        hide=True,
    )
    print('Your dumps bag has been emptied successfully.')


def _download_from_dumpbag(ctx, s3_path_dump):
    """Download one dump from Dump-bag with Aws.

    :param s3_path_dump: complete S3 path of dump
        as s3://odoo-dumps/fighting_snail_1024/fighting_snail_1024[...].pg.gpg
    """
    ctx.run("aws --profile=odoo-dumps s3 cp {} .".format(s3_path_dump))


def _get_list_of_dumps(ctx, database_name):
    """Download one dump from Dump-bag with Aws.

    :param database_name: database name or equal to S3 folder
        eg: is fighting_snail_1024 for case of
        s3://odoo-dumps/fighting_snail_1024/fighting_snail_1024[...].pg.gpg
    :return json.loads(result_of_aws_call): a list of all dump for one
        customer in dumpbag
    """
    # TODO should be available as "public task"

    result_of_aws_call = ctx.run(
        "aws --profile=odoo-dumps s3api list-objects-v2 \
        --bucket odoo-dumps --query 'Contents[].Key' \
        --prefix {}".format(
            database_name
        ),
        hide=True,
    ).stdout.strip()

    return json.loads(result_of_aws_call)
