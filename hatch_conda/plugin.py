from __future__ import annotations

import sys
from contextlib import contextmanager

from hatch.env.plugin.interface import EnvironmentInterface


class CondaEnvironment(EnvironmentInterface):
    PLUGIN_NAME = 'conda'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self._config_command = None
        self._config_conda_forge = None
        self.__python_version = None

        self.conda_env_name = f'{self.metadata.core.name}_{self.name}_{self.python_version}'
        self.project_path = '.'

    @staticmethod
    def get_option_types():
        return {'command': str, 'conda-forge': bool}

    def _config_value(self, field_name, default, valid=None):
        class_name = f'_config_{field_name.replace("-", "_")}'
        if self.__dict__[class_name] is None:
            value = self.config.get(field_name, default)
            if not isinstance(value, self.get_option_types()[field_name]):
                raise TypeError(
                    f'Field `tool.hatch.envs.{self.name}.{field_name}` must be a '
                    + '`{self.get_option_types()[field_name]}`'
                )
            if valid is not None and value not in valid:
                raise ValueError(f'Field `tool.hatch.envs.{self.name}.{field_name}` must be any of [{valid}] values.')
            self.__dict__[class_name] = value
        return self.__dict__[class_name]

    @property
    def config_command(self):
        return self._config_value('command', 'conda', ['conda', 'mamba'])

    @property
    def config_conda_forge(self):
        return self._config_value('conda-forge', True)

    @property
    def python_version(self):
        if self.__python_version is None:
            python_version = self.config.get('python', '')
            if not python_version:
                python_version = '.'.join(map(str, sys.version_info[:2]))
            elif python_version.isdigit() and len(python_version) > 1:
                python_version = f'{python_version[0]}.{python_version[1:]}'

            self.__python_version = python_version

        return self.__python_version

    def _get_conda_env_path(self, name):
        output = self.platform.check_command_output([self.config_command, 'env', 'list'])
        env_names, env_paths = zip(
            *[(line.split(' ')[0], line.split(' ')[-1]) for line in output.splitlines() if len(line.split(' ')[0]) > 1]
        )
        if name not in env_names:
            return None
        return env_paths[env_names.index(name)]

    def find(self):
        return self._get_conda_env_path(self.conda_env_name)

    def create(self):
        command = [
            self.config_command,
            'create',
            '-y',
            '-n',
            self.conda_env_name,
        ]
        if self.config_conda_forge:
            command += [
                '-c',
                'conda-forge',
                '--no-channel-priority',
            ]
        command += [
            f'python={self.python_version}',
            'pip',
        ]
        if self.verbosity > 0:  # no cov
            self.platform.check_command(command)
        else:
            self.platform.check_command_output(command)

    def remove(self):
        self.platform.check_command_output([self.config_command, 'env', 'remove', '-y', '--name', self.conda_env_name])

    def exists(self):
        return bool(self._get_conda_env_path(self.conda_env_name))

    def construct_conda_run_command(self, command):
        return [self.config_command, 'run', '-n', self.conda_env_name] + command

    def construct_pip_install_command(self, *args, **kwargs):
        return self.construct_conda_run_command(super().construct_pip_install_command(*args, **kwargs))

    def install_project(self):
        with self:
            self.platform.check_command(self.construct_pip_install_command([self.apply_features(self.project_path)]))

    def install_project_dev_mode(self):
        with self:
            self.platform.check_command(
                self.construct_pip_install_command(['--editable', self.apply_features(self.project_path)])
            )

    def dependencies_in_sync(self):
        if not self.dependencies:
            return True

        with self:
            process = self.platform.run_command(
                ' '.join(['hatchling', 'dep', 'synced', '-p', 'python', *self.dependencies]),
                capture_output=True,
            )
            return not process.returncode

    def sync_dependencies(self):
        with self:
            self.platform.check_command(self.construct_pip_install_command(self.dependencies))

    @contextmanager
    def command_context(self):
        with self:
            yield

    def run_shell_command(self, command):
        return self.platform.run_command(
            ' '.join(
                self.construct_conda_run_command(
                    [
                        command,
                    ]
                )
            )
        )

    def enter_shell(self, name, path, args):  # no cov
        with self:
            process = self.platform.run_command(' '.join([self.config_command, 'activate', self.conda_env_name]))
            self.platform.exit_with_code(process.returncode)
