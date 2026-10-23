# Combines the coverage data files in a folder into /mnt/extra-addons/coverage.xml, inside a container with Python.
# Usage: bash test_core_coverage.sh <data dir>
set -e
. "$(dirname "$0")/test_core_common.sh"

install_coverage
cd /mnt/extra-addons
python3 -m coverage combine -q --data-file="$1/.coverage" "$1"
python3 -m coverage xml -q --data-file="$1/.coverage" -o coverage.xml
sed -i 's|<source>/mnt/extra-addons</source>|<source>.</source>|' coverage.xml
