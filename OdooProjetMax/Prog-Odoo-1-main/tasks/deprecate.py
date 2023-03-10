# -*- coding: utf-8 -*-
# Copyright 2017 Camptocamp SA
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)
from __future__ import print_function

import os
import re

from invoke import task

from .common import (
    MIGRATION_FILE,
    PENDING_MERGES_DIR,
    build_path,
    cd,
    check_git_diff,
    exit_msg,
    root_path,
    search_replace,
)
from .submodule import Repo

try:
    from ruamel.yaml import YAML, round_trip_dump
except ImportError:
    print('Missing install ruamel.yaml from requirements')
    print('Please run `pip install -r tasks/requirements.txt`')


@task(name='demo-to-sample')
def demo_to_sample(ctx):
    """ Renaming of demo to sample for MARABUNTA_MODE

    This intend to fix files that aren't synced

    It will edit the following files:
    - .travis.yml
    - docker-compose.overide.yml
    - odoo/migration.yml
    - odoo/songs/install/data_all.py (for comment)
    - test.yml
    - travis/minion-files/rancher.list

    It will move:
    - odoo/data/demo to odoo/data/sample
    - odoo/songs/install/data_demo.py to odoo/songs/sample/data_sample.py

    """
    change_list = []
    # .travis.yml
    path = build_path('.travis.yml')
    search_replace(path, '-e MARABUNTA_MODE=demo', '-e MARABUNTA_MODE=sample')
    change_list.append(path)

    # docker-compose.overide.yml
    path = build_path('docker-compose.override.yml')
    if os.path.exists(path):
        search_replace(
            path, '- MARABUNTA_MODE=demo', '- MARABUNTA_MODE=sample'
        )
        change_list.append(path)

    # odoo/migration.yml
    path = MIGRATION_FILE
    search_replace(
        path,
        'anthem songs.install.data_demo',
        'anthem songs.sample.data_sample',
    )
    change_list.append(path)

    yaml = YAML()
    # preservation of indentation
    yaml.indent(mapping=2, sequence=4, offset=2)

    # change demo: keys to sample:
    with open(MIGRATION_FILE) as f:
        data = yaml.load(f.read())

    for x in data['migration']['versions']:
        if 'modes' in x and 'demo' in x['modes']:
            x['modes']['sample'] = x['modes']['demo']
            del x['modes']['demo']

    with open(MIGRATION_FILE, 'w') as f:
        yaml.dump(data, f)

    # test.yml
    path = build_path('odoo/songs/install/data_all.py')
    if os.path.exists(path):
        search_replace(
            path,
            "The data loaded here will be loaded in the 'demo' and",
            "The data loaded here will be loaded in the 'sample' and",
        )
        change_list.append(path)

    # test.yml
    path = build_path('test.yml')
    if os.path.exists(path):
        search_replace(
            path, '- MARABUNTA_MODE=demo', '- MARABUNTA_MODE=sample'
        )
        change_list.append(path)

    # travis/minion-files/rancher.list
    path = build_path('travis/minion-files/rancher.list')
    if os.path.exists(path):
        search_replace(path, 'MARABUNTA_MODE=demo', 'MARABUNTA_MODE=sample')
        change_list.append(path)

    ctx.run('git add {}'.format(' '.join(change_list)))

    folder = 'odoo/data/sample'
    try:
        os.mkdir(folder, 0o775)
    except OSError:
        print("odoo/data/sample directory already exists")
    # move odoo/data/demo to odoo/data/sample
    try:
        ctx.run('git mv {} {}'.format('odoo/data/demo/*', 'odoo/data/sample'))
    except Exception:
        print('nothing to move')

    # move odoo/songs/install/data_demo.py to odoo/songs/sample/data_sample.py
    folder = 'odoo/songs/sample'
    try:
        os.mkdir(folder, 0o775)
        with open(folder + '/__init__.py', 'w') as f:
            f.write('')
    except OSError:
        print("odoo/songs/sample directory already exists")
    try:
        ctx.run(
            'git mv {} {}'.format(
                'odoo/songs/install/data_demo.py',
                'odoo/songs/sample/data_sample.py',
            )
        )
    except Exception:
        print('nothing to move')

    # Change strings referencing 'data/demo' to 'data/sample'
    path = build_path('odoo/songs/sample/data_sample.py')
    if os.path.exists(path):
        search_replace(path, 'data/demo', 'data/sample')
        change_list.append(path)

    ctx.run('git add odoo/songs/sample')

    print("Deprecation applied")
    print()
    print("The following files were checked and modified:")
    print("- .travis.yml")
    print("- docker-compose.overide.yml")
    print("- odoo/migration.yml")
    print("- odoo/songs/install/data_all.py (for comment)")
    print(
        "- odoo/songs/install/data_demo.py (path 'data/demo' to "
        "'data/sample')"
    )
    print("- test.yml")
    print("- travis/minion-files/rancher.list")

    print()
    print("The following files were moved:")
    print("- odoo/data/demo to odoo/data/sample")
    print(
        "- odoo/songs/install/data_demo.py to odoo/songs/sample/data_sample"
        ".py"
    )
    print()
    print("Please check your staged files:")
    print("   git diff --cached")
    print(
        "Please search for any unchanged 'demo' string in odoo/songs "
        "and fix it manually."
    )
    print("If everything is good:")
    print("   git commit -m 'Apply depreciation of demo in favor of sample'")
    print("      git push")


@task
def split_pending_merges(ctx):
    """Split odoo/pending-merges.yaml to per-project files.

    It will remove:
    - odoo/pending-merges.yaml

    It will create following directory:
    - pending-merges.d/

    That directory will be populated with one YAML file per submodule, each
    holding it's own pending merges configuration.

    It'll try to commit applied changes afterwards
    """
    # both are relative to project root
    # that's for the sake of being able to commit changes afterwards
    old_path = build_path('odoo/pending-merges.yaml')

    # check if there's a file can be found by the old path
    # - that defines if we should even do smth at all
    if not os.path.exists(build_path(old_path)):
        exit_msg(
            'No file found at {}.\nNothing to do here!'.format(
                build_path(old_path)
            )
        )

    # we're gonna commit it afterwards, make sure that user is aware of it
    check_git_diff(ctx)

    # create a directory to store module local merges
    if not os.path.exists(PENDING_MERGES_DIR):
        os.makedirs(build_path(PENDING_MERGES_DIR))

    # read the old file, group stuff by modules
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    with open(build_path(old_path)) as pending_merges_file:
        data = yaml.load(
            '\n'.join(
                line
                for line in pending_merges_file.read().splitlines()
                if line.strip()
            )
        )
        for submodule_relpath in data:
            submodule_merges_path = Repo.build_submodule_merges_path(
                submodule_relpath
            )
            submodule_config = data[submodule_relpath]
            # rewrite relative submodule path
            patched_path = submodule_relpath.replace(
                './src/', '../odoo/src/', 1
            ).replace('./external-src/', '../odoo/external-src/', 1)
            # using dicts here is fine, cause we don't care about remotes order
            submodule_config['remotes'] = {
                re.sub(r'\boca\b', 'OCA', remote): url
                for remote, url in submodule_config['remotes'].items()
            }
            # different story w/ merges
            # we want to preserve comments, thus we have to dump the
            # whole thing and work with the strings if we don't
            # want to loose them. Comments are saved as separated
            # data in a CommentedMap.
            merges = round_trip_dump(submodule_config['merges']).split('\n')
            merges = [re.sub(r'\boca\b', 'OCA', merge) for merge in merges]
            submodule_config['merges'] = yaml.load('\n'.join(merges))
            with open(submodule_merges_path, 'w') as submodule_merges:
                yaml.dump({patched_path: submodule_config}, submodule_merges)

    with cd(root_path()):
        # git only works w/ relative paths, PENDING_MERGES_DIR is real
        ctx.run('git add -- {}'.format('pending-merges.d'))
        ctx.run('git rm -- {}'.format(old_path))
        commit_msg = 'Split odoo/pending-merges.yaml to per-submodule files'
        ctx.run("git commit -m '{}' -e -vv".format(commit_msg), pty=True)
