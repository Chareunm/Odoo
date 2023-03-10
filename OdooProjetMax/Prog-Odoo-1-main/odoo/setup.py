from setuptools import find_packages, setup

with open("VERSION") as fd:
    version = fd.read().strip()

setup(
    name="iut-odoo",
    version=version,
    description="IUT Odoo",
    license="GNU Affero General Public License v3 or later (AGPLv3+)",
    author="Kal-It",
    author_email="info@kal-it.fr",
    url="kal-it.fr",
    packages=["songs"] + ["songs.%s" % p for p in find_packages("./songs")],
    include_package_data=True,
    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved",
        "License :: OSI Approved :: "
        "GNU Affero General Public License v3 or later (AGPLv3+)",
        "Programming Language :: Python",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: Implementation :: CPython",
    ],
)
