#!/usr/bin/env python

import unittest
import mock
import os
import sys
import yaml
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from mountmon import mountmon

class MountTestCases(unittest.TestCase):

    def side_effect():
        raise(IOError)

    @mock.patch('os.listdir')
    @mock.patch('os.path.ismount')
    @mock.patch('mountmon.logging')
    def test_mountmon(self, mock_logging, mock_ismount, mock_listdir):

        reference = mountmon()
        reference.SetLogging()

        mountpoint = next(iter(reference.cfg['mountpoints']))
        filepath = "{}/foo".format(mountpoint)

        mock_ismount.return_value = False
        reference.MountMon(mountpoint)
        self.assertEqual(1, reference.MountMon(mountpoint))

        mock_ismount.return_value = True
        mock_listdir.side_effect = OSError('broken')
        self.assertEqual(2, reference.MountMon(mountpoint))

        mock_listdir.side_effect = None
        open_mock = mock.mock_open()
        with mock.patch('mountmon.open', open_mock):
            self.assertEqual(0, reference.MountMon(mountpoint))

            open_mock.side_effect = IOError('broken')
            self.assertEqual(4, reference.MountMon(mountpoint))


if __name__ == '__main__':
    unittest.main()
