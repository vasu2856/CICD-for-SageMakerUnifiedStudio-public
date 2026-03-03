"""Unit tests for DomainConfig class."""

import pytest
from unittest.mock import patch
from smus_cicd.application.application_manifest import DomainConfig


class TestDomainConfigGetName:
    """Test DomainConfig.get_name() method."""

    def test_get_name_with_explicit_name(self):
        """Test get_name returns explicit name when set."""
        config = DomainConfig(name="my-domain", region="us-east-1")
        assert config.get_name() == "my-domain"

    def test_get_name_with_tags_resolves_from_api(self):
        """Test get_name resolves domain name from tags via API."""
        config = DomainConfig(
            tags={"purpose": "smus-cicd-testing"}, region="us-east-2"
        )

        with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_resolve:
            mock_resolve.return_value = ("dzd-123456", "resolved-domain-name")
            result = config.get_name()

        assert result == "resolved-domain-name"
        mock_resolve.assert_called_once_with(
            domain_tags={"purpose": "smus-cicd-testing"}, region="us-east-2"
        )

    def test_get_name_with_tags_returns_none_when_not_found(self):
        """Test get_name returns None when domain not found by tags."""
        config = DomainConfig(tags={"purpose": "nonexistent"}, region="us-east-1")

        with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_resolve:
            mock_resolve.return_value = (None, None)
            result = config.get_name()

        assert result is None

    def test_get_name_prefers_explicit_name_over_tags(self):
        """Test get_name prefers explicit name even when tags are present."""
        config = DomainConfig(
            name="explicit-name",
            tags={"purpose": "test"},
            region="us-east-1",
        )

        # Should not call resolve_domain_id since name is set
        with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_resolve:
            result = config.get_name()

        assert result == "explicit-name"
        mock_resolve.assert_not_called()

    def test_get_name_returns_none_when_no_name_or_tags(self):
        """Test get_name returns None when neither name nor tags are set."""
        config = DomainConfig(region="us-east-1")
        assert config.get_name() is None

    def test_get_name_with_id_resolves_from_api(self):
        """Test get_name resolves domain name from id via API."""
        config = DomainConfig(id="dzd-abc123", region="us-east-1")

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_get:
            mock_get.return_value = "resolved-domain-name"
            result = config.get_name()

        assert result == "resolved-domain-name"
        mock_get.assert_called_once_with("dzd-abc123", "us-east-1")

    def test_get_name_with_id_returns_none_when_not_found(self):
        """Test get_name returns None when domain not found by id."""
        config = DomainConfig(id="dzd-nonexistent", region="us-east-1")

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_get:
            mock_get.return_value = None
            result = config.get_name()

        assert result is None

    def test_get_name_prefers_explicit_name_over_id(self):
        """Test get_name prefers explicit name even when id is also present."""
        config = DomainConfig(name="explicit-name", id="dzd-abc123", region="us-east-1")

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_get:
            result = config.get_name()

        assert result == "explicit-name"
        mock_get.assert_not_called()

    def test_get_name_prefers_id_over_tags(self):
        """Test get_name uses id before falling back to tags."""
        config = DomainConfig(
            id="dzd-abc123",
            tags={"purpose": "test"},
            region="us-east-1",
        )

        with patch("smus_cicd.helpers.datazone.get_domain_name_by_id") as mock_id:
            mock_id.return_value = "id-resolved-name"
            with patch("smus_cicd.helpers.datazone.resolve_domain_id") as mock_tags:
                result = config.get_name()

        assert result == "id-resolved-name"
        mock_id.assert_called_once()
        mock_tags.assert_not_called()


class TestDomainConfigParsing:
    """Test DomainConfig is parsed correctly from manifest dict."""

    def test_manifest_parses_domain_id(self):
        """Test that domain.id is parsed from manifest and stored on DomainConfig."""
        from smus_cicd.application.application_manifest import ApplicationManifest

        data = {
            "applicationName": "TestApp",
            "content": {"workflows": [{"workflowName": "wf", "connectionName": "c"}]},
            "stages": {
                "dev": {
                    "domain": {
                        "id": "dzd-abc123",
                        "region": "us-east-1",
                    },
                    "project": {"name": "my-project"},
                }
            },
        }

        manifest = ApplicationManifest.from_dict(data)
        assert manifest.stages["dev"].domain.id == "dzd-abc123"
        assert manifest.stages["dev"].domain.name is None
        assert manifest.stages["dev"].domain.tags is None

# Trigger workflow - Fri Nov 21 16:56:07 EST 2025
