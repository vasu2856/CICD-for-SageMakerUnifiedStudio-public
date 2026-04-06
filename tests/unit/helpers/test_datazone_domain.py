"""Unit tests for domain resolution in datazone helpers."""

import pytest
from unittest.mock import MagicMock, patch

from smus_cicd.application.application_manifest import DomainConfig, StageConfig, ProjectConfig
from smus_cicd.helpers.datazone import get_domain_from_target_config


def _make_target(domain_id=None, domain_name=None, domain_tags=None, region="us-east-1"):
    """Helper to build a minimal StageConfig with the given domain fields."""
    domain = DomainConfig(region=region, id=domain_id, name=domain_name, tags=domain_tags)
    project = ProjectConfig(name="my-project")
    return StageConfig(project=project, domain=domain, stage="DEV")


class TestGetDomainFromTargetConfigWithId:
    """Test get_domain_from_target_config when domain.id is provided."""

    def test_returns_id_and_resolved_name(self):
        """When domain.id is set, returns it directly and resolves name via API."""
        target = _make_target(domain_id="dzd-abc123")

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_get:
            mock_get.return_value = "my-domain"
            domain_id, domain_name = get_domain_from_target_config(target)

        assert domain_id == "dzd-abc123"
        assert domain_name == "my-domain"
        mock_get.assert_called_once_with("dzd-abc123", "us-east-1")

    def test_raises_when_id_not_found(self):
        """When domain.id is set but not found, raises an exception."""
        target = _make_target(domain_id="dzd-nonexistent")

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_get:
            mock_get.return_value = None
            with pytest.raises(Exception, match="dzd-nonexistent"):
                get_domain_from_target_config(target)

    def test_id_takes_priority_over_name(self):
        """When both domain.id and domain.name are set, id is used."""
        target = _make_target(domain_id="dzd-abc123", domain_name="should-be-ignored")

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_id:
            mock_id.return_value = "id-resolved-name"
            with patch("smus_cicd.helpers.datazone.get_domain_id_by_name") as mock_name:
                domain_id, domain_name = get_domain_from_target_config(target)

        assert domain_id == "dzd-abc123"
        assert domain_name == "id-resolved-name"
        mock_id.assert_called_once()
        mock_name.assert_not_called()

    def test_id_takes_priority_over_tags(self):
        """When both domain.id and domain.tags are set, id is used."""
        target = _make_target(domain_id="dzd-abc123", domain_tags={"purpose": "test"})

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_id:
            mock_id.return_value = "id-resolved-name"
            with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_tags:
                domain_id, domain_name = get_domain_from_target_config(target)

        assert domain_id == "dzd-abc123"
        mock_id.assert_called_once()
        mock_tags.assert_not_called()

    def test_region_override_is_respected(self):
        """Region override parameter is passed through to the API call."""
        target = _make_target(domain_id="dzd-abc123", region="us-east-1")

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_get:
            mock_get.return_value = "my-domain"
            get_domain_from_target_config(target, region="eu-west-1")

        mock_get.assert_called_once_with("dzd-abc123", "eu-west-1")


class TestGetDomainNameById:
    """Test get_domain_name_by_id helper."""

    def test_returns_domain_name(self):
        """Returns the domain name from get_domain API response."""
        from smus_cicd.helpers.datazone import get_domain_name_by_id

        mock_client = MagicMock()
        mock_client.get_domain.return_value = {"id": "dzd-abc123", "name": "my-domain"}

        with patch("smus_cicd.helpers.datazone._get_datazone_client", return_value=mock_client):
            result = get_domain_name_by_id("dzd-abc123", "us-east-1")

        assert result == "my-domain"
        mock_client.get_domain.assert_called_once_with(identifier="dzd-abc123")

    def test_raises_on_api_error(self):
        """Propagates exceptions from the DataZone API."""
        from smus_cicd.helpers.datazone import get_domain_name_by_id

        mock_client = MagicMock()
        mock_client.get_domain.side_effect = Exception("ResourceNotFoundException")

        with patch("smus_cicd.helpers.datazone._get_datazone_client", return_value=mock_client):
            with pytest.raises(Exception, match="ResourceNotFoundException"):
                get_domain_name_by_id("dzd-bad", "us-east-1")


class TestResolveDomainIdAutoDetect:
    """Test _resolve_domain_id auto-detect path in utils (no id/name/tags provided)."""

    def test_auto_detects_single_domain(self):
        """When no domain id/name/tags are set, resolve_domain_id is called and auto-detects."""
        from smus_cicd.helpers.utils import _resolve_domain_id

        config = {"domain": {"region": "us-east-1"}}

        with patch("smus_cicd.helpers.utils.get_domain_id", return_value=None):
            with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_resolve:
                mock_resolve.return_value = ("dzd-autodetected", "auto-domain")
                result = _resolve_domain_id(config, "us-east-1")

        assert result == "dzd-autodetected"
        mock_resolve.assert_called_once_with(
            domain_name=None, domain_tags=None, region="us-east-1"
        )

    def test_raises_when_multiple_domains_and_no_identifier(self):
        """When multiple domains exist and no identifier given, raises an exception."""
        from smus_cicd.helpers.utils import _resolve_domain_id

        config = {"domain": {"region": "us-east-1"}}

        with patch("smus_cicd.helpers.utils.get_domain_id", return_value=None):
            with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_resolve:
                mock_resolve.side_effect = Exception(
                    "Multiple domains found in region us-east-1. Please specify domain name or tags."
                )
                with pytest.raises(Exception, match="Multiple domains found"):
                    _resolve_domain_id(config, "us-east-1")

    def test_cfn_result_takes_priority(self):
        """When CloudFormation returns a domain ID, it is used without calling resolve_domain_id."""
        from smus_cicd.helpers.utils import _resolve_domain_id

        config = {"domain": {"region": "us-east-1"}}

        with patch("smus_cicd.helpers.utils.get_domain_id", return_value="dzd-from-cfn"):
            with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_resolve:
                result = _resolve_domain_id(config, "us-east-1")

        assert result == "dzd-from-cfn"
        mock_resolve.assert_not_called()

    def test_direct_id_skips_resolve(self):
        """When domain.id is set, resolve_domain_id is not called."""
        from smus_cicd.helpers.utils import _resolve_domain_id

        config = {"domain": {"id": "dzd-direct", "region": "us-east-1"}}

        with patch("smus_cicd.helpers.utils.get_domain_id", return_value=None):
            with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_resolve:
                result = _resolve_domain_id(config, "us-east-1")

        assert result == "dzd-direct"
        mock_resolve.assert_not_called()

