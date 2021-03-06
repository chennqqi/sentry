import {Box} from 'grid-emotion';
import PropTypes from 'prop-types';
import React from 'react';

import SettingsNavigationGroup from 'app/views/settings/components/settingsNavigationGroup';
import SentryTypes from 'app/sentryTypes';
import HookStore from 'app/stores/hookStore';

class SettingsNavigation extends React.Component {
  static propTypes = {
    hooks: PropTypes.array,
    hookConfigs: PropTypes.array,
    navigationObjects: PropTypes.arrayOf(SentryTypes.NavigationObject).isRequired,
    organization: SentryTypes.Organization,
  };

  static defaultProps = {
    hooks: [],
    hookConfigs: [],
  };

  componentDidMount() {
    let {organization} = this.props;
    if (!organization) return;
    let features = organization.features;

    //Experiment variant is already assigned - this logs the exposure i.e. when the user gets to the settings page
    let treatment = features.includes('sso-paywall-experiment-treatment');
    let control = features.includes('sso-paywall-experiment-control');

    // Only want to log the people in the experiment
    if (!treatment && !control) return;

    let data = {
      experiment_name: 'SSOPaywallExperiment',
      unit_name: 'org_id',
      unit_id: parseInt(organization.id, 10),
      params: `{exposed: ${treatment ? 1 : 0}}`,
    };

    HookStore.get('analytics:log-experiment').forEach(cb => cb(data));
  }

  render() {
    let {navigationObjects, hooks, hookConfigs, ...otherProps} = this.props;
    let navWithHooks = navigationObjects.concat(hookConfigs);

    return (
      <Box>
        {navWithHooks.map(config => (
          <SettingsNavigationGroup key={config.name} {...otherProps} {...config} />
        ))}
        {hooks.map((Hook, i) =>
          React.cloneElement(Hook, {
            key: `hook-${i}`,
          })
        )}
      </Box>
    );
  }
}

export default SettingsNavigation;
