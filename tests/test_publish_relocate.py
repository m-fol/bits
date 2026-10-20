# SPDX-FileCopyrightText: 2026 CERN
# SPDX-License-Identifier: GPL-3.0-or-later

"""bits publish PACKAGE: the copy is relocated and published, the install is not touched."""

import argparse
import hashlib
import os
import shutil
import tempfile
import unittest
from unittest import mock

import bits_helpers
from bits_helpers import publish

ARCH, PKG, VER = "slc9_x86-64", "zlib", "v1.3.1-1"
PP = "%s/%s/%s" % (ARCH, PKG, VER)
TARGET = "/cvmfs/repo.example/Packages/zlib/1.3.1"


def digest(root):
  h = hashlib.sha256()
  for dp, dns, fns in os.walk(root):
    dns.sort()
    for name in sorted(fns):
      p = os.path.join(dp, name)
      h.update(os.path.relpath(p, root).encode())
      if os.path.islink(p):
        h.update(os.readlink(p).encode())
      else:
        with open(p, "rb") as f:
          h.update(f.read())
  return h.hexdigest()


class PublishRelocateTest(unittest.TestCase):
  def setUp(self):
    self.base = tempfile.mkdtemp()
    self.addCleanup(shutil.rmtree, self.base, True)
    self.work = os.path.join(self.base, "sw")
    self.inst = os.path.join(self.work, PP)
    os.makedirs(os.path.join(self.inst, "etc", "profile.d"))
    os.makedirs(os.path.join(self.inst, "etc", "modulefiles"))
    with open(os.path.join(os.path.dirname(bits_helpers.__file__), "relocate-me.sh")) as f:
      script = f.read()
    script += ("mv -f $PP/etc/modulefiles/%s $PP/etc/modulefiles/%s.forced-relocation && "
               "cp $PP/etc/modulefiles/%s.forced-relocation $PP/etc/modulefiles/%s\n"
               % (PKG, PKG, PKG, PKG))
    with open(os.path.join(self.inst, "relocate-me.sh"), "w") as f:
      f.write(script)
    with open(os.path.join(self.inst, "etc", "profile.d", ".bits-pkginfo"), "w") as f:
      f.write('OP=%s\nPP=${PKGPATH:-%s}\nPH=abc123\nPKG_DIR="%s"\n' % (PP, PP, self.work))
    with open(os.path.join(self.inst, "etc", "profile.d", ".bits-relocate"), "w") as f:
      f.write("etc/profile.d/init.sh\n")
    with open(os.path.join(self.inst, "etc", "profile.d", "init.sh"), "w") as f:
      f.write("export ZLIB_ROOT=%s/%s\nexport LIBS=%s/%s/lib\n" % (self.work, PP, self.work, PP))
    with open(os.path.join(self.inst, "etc", "modulefiles", PKG), "w") as f:
      f.write("#%Module1.0\n")
    os.symlink(VER, os.path.join(self.work, ARCH, PKG, "latest"))
    self.published = []

  def _publish_tree(self, tree_dir, repo, subpath, cfg, what):
    dest = os.path.join(self.base, "published%d" % len(self.published))
    shutil.copytree(tree_dir, dest, symlinks=True)
    self.published.append(dest)

  def _publish(self, no_relocate=False):
    args = argparse.Namespace(
      package=PKG, version=None, workDir=self.work, architecture=ARCH,
      cvmfsTarget=TARGET, prepubUrl="https://prepub.invalid", prepubToken=None,
      prepubRepo=None, prepubPath=None, prepubWebhook=None, prepubPollInterval=1,
      prepubTimeout=1, prepubNoVerifyTls=False, prepubBearerAuth=False,
      scratchDir=None, noRelocate=no_relocate, moduleTarget=None,
      fromManifest=None, publishView=None, dryRun=False)
    with mock.patch.object(publish, "_publish_tree", self._publish_tree):
      return publish.doPublish(args, argparse.ArgumentParser())

  def _init(self, root):
    with open(os.path.join(root, "etc", "profile.d", "init.sh")) as f:
      return f.read().split()

  def test_the_copy_is_relocated_and_the_install_is_untouched(self):
    before = digest(self.work)
    self.assertTrue(self._publish())
    self.assertEqual(digest(self.work), before)
    self.assertEqual(len(self.published), 1)
    self.assertEqual(self._init(self.published[0]),
                     ["export", "ZLIB_ROOT=%s" % TARGET, "export", "LIBS=%s/lib" % TARGET])
    self.assertTrue(os.path.isfile(os.path.join(
      self.published[0], "etc", "modulefiles", PKG + ".forced-relocation")))

  def test_no_relocate_publishes_the_install_as_is(self):
    before = digest(self.work)
    self.assertTrue(self._publish(no_relocate=True))
    self.assertEqual(digest(self.work), before)
    self.assertEqual(self._init(self.published[0]), self._init(self.inst))


if __name__ == "__main__":
  unittest.main()
