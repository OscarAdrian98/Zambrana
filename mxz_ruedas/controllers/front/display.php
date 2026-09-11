<?php
class Mxz_RuedasDisplayModuleFrontController extends ModuleFrontController
{
    public function initContent()
    {
        parent::initContent();
        $this->context->smarty->assign(array(
            'module_dir' => $this->module->getPathUri(),
        ));
        $this->setTemplate('module:mxz_ruedas/views/templates/front/display.tpl');
    }
}
