<?php
if (!defined('_PS_VERSION_')) {
    exit;
}

class Mxz_Ruedas extends Module
{
    public function __construct()
    {
        $this->name = 'mxz_ruedas';
        $this->tab = 'front_office_features';
        $this->version = '1.0.0';
        $this->author = 'MxZambrana';
        $this->need_instance = 0;
        $this->bootstrap = true;

        parent::__construct();

        $this->displayName = $this->l('Configurador Ruedas Moto');
        $this->description = $this->l('Módulo para mostrar un configurador estético de tu moto con las ruedas de Haan');

        $this->ps_versions_compliancy = array('min' => '1.7.0.0', 'max' => _PS_VERSION_);
    }

    public function install()
    {
        return parent::install() && $this->registerHook('header');
    }

    public function hookHeader()
    {
        $this->context->controller->addCSS($this->_path . 'views/css/style.css', 'all');
        $this->context->controller->addJS($this->_path . 'views/js/script.js');
    }
}
